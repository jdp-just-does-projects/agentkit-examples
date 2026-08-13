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

"""Runtime patches shared by every service of this sample.

Import this module before importing the agent so all sub-agent models are
patched consistently: `import workarounds  # noqa: F401`. Each service ships
its own copy of this file because the services are deployed as standalone
units with no shared package (the same duplication pattern as `app.py`).
"""

import json
import logging

from google.adk.models.lite_llm import LiteLlm
from veadk.models.ark_llm import ArkLlm

logger = logging.getLogger(__name__)

#### Start of workaround

# The Dev UI's /dev/apps/{app}/build_graph endpoint serializes the agent's model
# with model_dump(mode="python") (see google/adk/cli/utils/graph_serialization.py),
# which leaves the live `llm_client` handle in the payload. FastAPI then fails to
# encode it as JSON and the endpoint returns 500. Marking the field as excluded
# keeps the client on the instance for generation while dropping it from every
# dump. Still required as of google-adk 2.2.0; recheck on future upgrades.
for _model_cls in (LiteLlm, ArkLlm):
    _field = _model_cls.model_fields.get("llm_client")
    if _field is not None and not _field.exclude:
        _field.exclude = True
        _model_cls.model_rebuild(force=True)

#### END OF WORKAROUND

#### Start of workaround

# The agent model occasionally emits tool-call arguments that are not strictly
# valid JSON (e.g. an unescaped quote inside a long image/video prompt).
# google-adk's _parse_tool_call_arguments only repairs unquoted object keys and
# otherwise re-raises, which aborts the entire workflow run with a
# JSONDecodeError. Still the case as of google-adk 2.2.0; recheck on upgrades.
# Fall back to json-repair, and log the raw payload so genuinely unrecoverable
# calls can be diagnosed instead of guessing at the model output.
import google.adk.models.lite_llm as _lite_llm  # noqa: E402
from json_repair import repair_json  # noqa: E402

_original_parse_tool_call_arguments = _lite_llm._parse_tool_call_arguments


def _parse_tool_call_arguments_with_repair(arguments):
    try:
        return _original_parse_tool_call_arguments(arguments)
    except json.JSONDecodeError:
        logger.warning(
            "Model produced malformed tool-call arguments, attempting repair: %r",
            arguments,
        )
        repaired = repair_json(arguments, return_objects=True)
        if isinstance(repaired, dict) and repaired:
            return repaired
        raise


_lite_llm._parse_tool_call_arguments = _parse_tool_call_arguments_with_repair

#### END OF WORKAROUND

#### Start of workaround

# This sample's agents keep `enable_responses` at its default (False), so the
# lite_llm patch above covers the actual runtime path. However, if a user
# enables the Ark Responses API via config, requests go through veadk's ArkLlm
# instead, where tool-call arguments are parsed with a bare
# `json.loads(output.arguments)` in event_to_generate_content_response
# (veadk/models/ark_llm.py) — the same failure mode as above. Repair the
# arguments in place before veadk parses them; leave them untouched when repair
# fails so the original error still surfaces. Still required as of
# veadk-python 1.0.10; recheck on upgrades.
import veadk.models.ark_llm as _ark_llm  # noqa: E402

_original_event_to_generate_content_response = _ark_llm.event_to_generate_content_response


def _repair_ark_function_call_arguments(event):
    # Only full responses carry `output`; stream delta events do not.
    for output in getattr(event, "output", None) or []:
        if not isinstance(output, _ark_llm.ResponseFunctionToolCall):
            continue
        arguments = output.arguments
        if not arguments:
            continue
        try:
            json.loads(arguments)
        except json.JSONDecodeError:
            logger.warning(
                "Model produced malformed Responses-API tool-call arguments, "
                "attempting repair: %r",
                arguments,
            )
            repaired = repair_json(arguments, return_objects=True)
            if isinstance(repaired, dict) and repaired:
                output.arguments = json.dumps(repaired, ensure_ascii=False)


def _event_to_generate_content_response_with_repair(*args, **kwargs):
    event = kwargs.get("event", args[0] if args else None)
    if event is not None:
        _repair_ark_function_call_arguments(event)
    return _original_event_to_generate_content_response(*args, **kwargs)


# Both veadk call sites (streaming and non-streaming) resolve this function
# through module globals at call time, so patching the attribute covers both.
_ark_llm.event_to_generate_content_response = (
    _event_to_generate_content_response_with_repair
)

#### END OF WORKAROUND

#### Start of workaround

# Several services wrap multiple sub-agents (e.g. a generate agent followed by
# a format agent in a SequentialAgent), and every sub-agent sees the full
# session history, including tool calls made by earlier agents. The model
# occasionally imitates one of those calls even though the tool is not in its
# own tool list, and google-adk's _get_tool then raises ValueError
# ("Tool 'X' not found"), aborting the entire run after the earlier (expensive)
# stages already completed. Return the error to the model as a normal tool
# response instead, so it can correct itself and continue. Still required as of
# google-adk 2.2.0; recheck on upgrades.
import google.adk.flows.llm_flows.functions as _adk_functions  # noqa: E402
from google.adk.tools.function_tool import FunctionTool  # noqa: E402

_original_get_tool = _adk_functions._get_tool


def _get_tool_with_fallback(function_call, tools_dict):
    try:
        return _original_get_tool(function_call, tools_dict)
    except ValueError:
        available = ", ".join(tools_dict.keys())
        logger.warning(
            "Model called unknown tool %r (available: %s); "
            "returning the error to the model instead of aborting the run",
            function_call.name,
            available,
        )
        error_msg = (
            f"Error: tool '{function_call.name}' does not exist for this agent. "
            f"The only tools you can call are: {available}. Do not repeat tool "
            "calls made by other agents earlier in the conversation. Continue "
            "the task using only your own tools."
        )

        def _unknown_tool():
            return {"error": error_msg}

        fallback = FunctionTool(func=_unknown_tool)
        # Match the hallucinated name so the function response pairs with the
        # model's function call.
        fallback.name = function_call.name
        return fallback


_adk_functions._get_tool = _get_tool_with_fallback

#### END OF WORKAROUND
