# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""URL guard: stop the models from mistyping the asset URLs they relay.

Why this exists
---------------
Every stage of this pipeline hands asset URLs to the next one *through the
model*: the image tool returns a pre-signed TOS URL, the agent retypes it into
its JSON reply, the format agent copies that into ``image_list``, the
orchestrator relays it to the evaluate agent, and so on. Those URLs are ~500
characters of high-entropy query string:

    ...&X-Tos-Signature=<64 hex chars>&X-Tos-SignedHeaders=host

Token by token that is exactly the kind of text a language model reproduces
*almost* perfectly. In practice one URL in a run comes back with a duplicated
or dropped character somewhere in the signature, e.g. a 65-character
``X-Tos-Signature``. The URL still looks completely plausible, so nothing
downstream notices until ModelArk tries to fetch it and answers

    400 InvalidParameter - Error while downloading: <url>, status code: 403

which is not JSON, so the driver dies on ``json.loads`` with the famously
unhelpful ``Expecting value: line 1 column 1 (char 0)``.

What this does
--------------
``restore_urls`` is an ``after_model_callback``. For every complete model
response it looks at each URL the model just wrote and compares it against the
URLs this session has seen from sources the model cannot have mistyped:

* the payload of every ``function_response`` (raw tool output), and
* the text of every ``user`` message (what the caller handed this service).

An exact match is left alone. Anything else is fuzzy-matched against that
authoritative set; when one candidate is a clear, near-identical winner on the
same host, the model's version is replaced with it. A URL with no close match
(a product link the user typed, a page the search tool found) is left
untouched, so the guard only ever undoes corruption it can prove.

Both the visible text and the arguments of any ``function_call`` are repaired
— a mistyped URL passed *into* the next tool (the first frame handed to video
generation, say) fails exactly the same way as one passed to the caller.

Install it with ``install(root_agent)``, which walks the agent tree and puts
the callback in front of every LLM agent's existing ``after_model_callback``
chain. The callback repairs ``llm_response`` in place and returns ``None`` so
that the rest of the chain (``fix_output_format`` and friends) still runs —
ADK stops at the first callback that returns a response.
"""

from __future__ import annotations

import difflib
import json
import re
from typing import Any, Iterable, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

# Matches a URL and stops at the characters that realistically terminate one in
# JSON, Python reprs or prose. Trailing punctuation is trimmed separately.
_URL_RE = re.compile(r"https?://[^\s\"'<>\\`\]}),]+")

# How similar a model-written URL must be to an authoritative one before we
# treat it as a corrupted copy of it rather than a different URL. Real
# corruption is a character or two out of ~500, i.e. a ratio of ~0.998; two
# genuinely different pre-signed URLs for the same bucket still share their
# host and parameter names, which is why the bar has to be this high.
_MATCH_THRESHOLD = 0.97

# The winner must also beat the runner-up by this margin, so that a URL which
# is nearly equidistant from two candidates is left alone instead of being
# snapped to an arbitrary one of them.
_MATCH_MARGIN = 0.005


def _trim(url: str) -> str:
    """Drop trailing punctuation the URL regex may have swallowed."""
    return url.rstrip(".,;:!?'\"")


def _extract_urls(text: str) -> list[str]:
    return [_trim(match.group(0)) for match in _URL_RE.finditer(text)]


def _host(url: str) -> str:
    # Cheaper and more forgiving than urlparse on a possibly mangled URL.
    return url.split("//", 1)[-1].split("/", 1)[0]


def _authoritative_urls(callback_context: CallbackContext) -> set[str]:
    """URLs from this session that no model has retyped.

    Tool output and the caller's own message are ground truth; anything a
    model wrote is a copy and may carry the corruption we are looking for.
    """
    urls: set[str] = set()
    session = callback_context._invocation_context.session

    for event in session.events:
        content = getattr(event, "content", None)
        if content is None or not getattr(content, "parts", None):
            continue

        is_user_message = getattr(content, "role", None) == "user"
        for part in content.parts:
            function_response = getattr(part, "function_response", None)
            if function_response is not None:
                urls.update(_extract_urls(_stringify(function_response.response)))
                continue
            # Only trust free text when the *caller* wrote it. A user-role
            # part that carries a function_response is a tool result, already
            # handled above.
            if is_user_message and getattr(part, "text", None):
                urls.update(_extract_urls(part.text))

    return urls


def _stringify(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _best_match(url: str, candidates: Iterable[str]) -> Optional[str]:
    """The authoritative URL that ``url`` is a corrupted copy of, if any."""
    host = _host(url)
    scored: list[tuple[float, str]] = []
    for candidate in candidates:
        if _host(candidate) != host:
            continue
        # A corruption is a handful of characters; anything further apart in
        # length is a different URL, and comparing it is wasted work.
        if abs(len(candidate) - len(url)) > 8:
            continue
        ratio = difflib.SequenceMatcher(None, url, candidate).ratio()
        if ratio >= _MATCH_THRESHOLD:
            scored.append((ratio, candidate))

    if not scored:
        return None
    scored.sort(reverse=True)
    if len(scored) > 1 and scored[0][0] - scored[1][0] < _MATCH_MARGIN:
        logger.warning(
            "[url_guard] URL %s...%s matches several authoritative URLs equally "
            "well; leaving it untouched",
            url[:60],
            url[-24:],
        )
        return None
    return scored[0][1]


def _repair_text(text: str, authoritative: set[str], agent_name: str) -> tuple[str, int]:
    repairs = 0
    for written in dict.fromkeys(_extract_urls(text)):  # de-duplicated, ordered
        if written in authoritative:
            continue
        correct = _best_match(written, authoritative)
        if correct is None or correct == written:
            continue
        text = text.replace(written, correct)
        repairs += 1
        logger.warning(
            "[url_guard] %s mistyped a URL; restored it from the authoritative "
            "value (wrote ...%s, should be ...%s)",
            agent_name,
            written[-48:],
            correct[-48:],
        )
    return text, repairs


def _repair_args(value: Any, authoritative: set[str], agent_name: str) -> tuple[Any, int]:
    """Walk a function call's arguments, repairing every string in place."""
    if isinstance(value, str):
        if "http" not in value:
            return value, 0
        return _repair_text(value, authoritative, agent_name)
    if isinstance(value, dict):
        repairs = 0
        for key, item in value.items():
            value[key], fixed = _repair_args(item, authoritative, agent_name)
            repairs += fixed
        return value, repairs
    if isinstance(value, list):
        repairs = 0
        for index, item in enumerate(value):
            value[index], fixed = _repair_args(item, authoritative, agent_name)
            repairs += fixed
        return value, repairs
    return value, 0


def restore_urls(
    *,
    callback_context: CallbackContext,
    llm_response: LlmResponse,
    **_kwargs: Any,
) -> None:
    """Repair mistyped asset URLs in ``llm_response``, in place.

    Always returns ``None`` so the agent's remaining after-model callbacks
    still run.
    """
    # Streaming chunks split URLs across responses; only the assembled reply
    # can be compared meaningfully.
    if getattr(llm_response, "partial", False):
        return None

    content = getattr(llm_response, "content", None)
    if content is None or not getattr(content, "parts", None):
        return None

    try:
        authoritative = _authoritative_urls(callback_context)
    except Exception as e:  # never let the guard break a working run
        logger.warning(f"[url_guard] Could not collect authoritative URLs: {e}")
        return None

    if not authoritative:
        return None

    agent_name = callback_context._invocation_context.agent.name
    repairs = 0

    for part in content.parts:
        try:
            text = getattr(part, "text", None)
            if text and "http" in text:
                part.text, fixed = _repair_text(text, authoritative, agent_name)
                repairs += fixed

            function_call = getattr(part, "function_call", None)
            if function_call is not None and function_call.args:
                function_call.args, fixed = _repair_args(
                    function_call.args, authoritative, agent_name
                )
                repairs += fixed
        except Exception as e:
            logger.warning(f"[url_guard] Failed to repair a response part: {e}")

    if repairs:
        logger.warning(
            f"[url_guard] Restored {repairs} mistyped URL(s) in {agent_name}'s response"
        )
    return None


def install(agent: Any) -> None:
    """Put ``restore_urls`` in front of every LLM agent's after-model chain."""
    installed: list[str] = []

    def _walk(node: Any) -> None:
        # Only LLM agents have an after_model_callback; SequentialAgent and
        # friends just carry sub_agents.
        if hasattr(node, "after_model_callback"):
            existing = node.after_model_callback
            if existing is None:
                chain = []
            elif isinstance(existing, list):
                chain = list(existing)
            else:
                chain = [existing]
            if restore_urls not in chain:
                node.after_model_callback = [restore_urls, *chain]
                installed.append(node.name)
        for sub_agent in getattr(node, "sub_agents", None) or []:
            _walk(sub_agent)

    _walk(agent)
    logger.info(f"[url_guard] Installed on: {', '.join(installed) or '(no agents)'}")
