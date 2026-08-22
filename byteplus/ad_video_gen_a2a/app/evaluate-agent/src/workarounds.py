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

#### Start of workaround

# google-adk 2.2.0's RemoteA2aAgent (the base class of veadk's RemoteVeAgent)
# calls `self._a2a_client.send_message(request=..., request_metadata=...,
# context=...)` in remote_a2a_agent.py, but veadk-python 1.1.2 pins
# a2a-sdk==0.3.7, whose `BaseClient.send_message` only accepts
# `(request, *, context)`. Every A2A hop therefore dies with
# "A2A request failed: BaseClient.send_message() got an unexpected keyword
# argument 'request_metadata'" and the orchestrator returns an event with no
# content at all. a2a-sdk added the parameter in a later 0.3.x release, where
# it is forwarded verbatim as `MessageSendParams.metadata`; back-port exactly
# that behaviour so the pinned combination works. The patch is a no-op on any
# a2a-sdk that already accepts the argument, so it can stay in place until
# veadk relaxes its pin.
import contextvars  # noqa: E402
import inspect  # noqa: E402

import a2a.client.base_client as _a2a_base_client  # noqa: E402

if (
    "request_metadata"
    not in inspect.signature(_a2a_base_client.BaseClient.send_message).parameters
):
    # `send_message` builds the MessageSendParams itself, so hand the metadata
    # down through a ContextVar (one context per asyncio task, so concurrent
    # A2A calls stay isolated) and inject it where the params are constructed.
    _pending_request_metadata = contextvars.ContextVar(
        "a2a_pending_request_metadata", default=None
    )
    _original_message_send_params = _a2a_base_client.MessageSendParams

    def _message_send_params_with_metadata(**kwargs):
        metadata = _pending_request_metadata.get()
        if metadata is not None and kwargs.get("metadata") is None:
            kwargs["metadata"] = metadata
        return _original_message_send_params(**kwargs)

    # Only rebind the name inside base_client (its single construction site);
    # a2a.types.MessageSendParams itself stays untouched for isinstance checks.
    _a2a_base_client.MessageSendParams = _message_send_params_with_metadata

    _original_send_message = _a2a_base_client.BaseClient.send_message

    async def _send_message_with_request_metadata(
        self, request, *, context=None, request_metadata=None
    ):
        token = _pending_request_metadata.set(request_metadata)
        try:
            async for event in _original_send_message(self, request, context=context):
                yield event
        finally:
            try:
                _pending_request_metadata.reset(token)
            except ValueError:
                # The generator was finalized in a different context than the
                # one that set the token; the stale value dies with it.
                pass

    _a2a_base_client.BaseClient.send_message = _send_message_with_request_metadata

#### END OF WORKAROUND

#### Start of workaround

# Every service's `format_agent` declares `output_schema=<pydantic model>` so
# ADK validates the structured result. google-adk 2.2.0 also forwards that
# schema to the provider as `response_format={"type": "json_schema", ...}`
# (lite_llm._to_litellm_response_format), but BytePlus ModelArk chat models
# such as deepseek-v4-pro-260425 only implement JSON mode, so the request is
# rejected with:
#   "The parameter `response_format.type` specified in the request are not
#    valid: `json_schema` is not supported by this model"
# and the agent returns that error string instead of the expected JSON.
# Fall back to `{"type": "json_object"}` whenever LiteLLM does not advertise
# schema support for the target model; the agents already pin the shape with
# their prompts and enforce it locally through their `output_schema`
# validation and the `fix_output_format*` after-model callbacks, so nothing is
# lost. Models that do support json_schema keep it. Still required as of
# google-adk 2.2.0; recheck on upgrades and when Ark adds schema support.
import litellm as _litellm  # noqa: E402

_original_to_litellm_response_format = _lite_llm._to_litellm_response_format


def _to_litellm_response_format_with_json_mode_fallback(response_schema, model):
    response_format = _original_to_litellm_response_format(
        response_schema, model=model
    )
    if (
        not isinstance(response_format, dict)
        or response_format.get("type") != "json_schema"
    ):
        return response_format

    try:
        supports_schema = _litellm.supports_response_schema(model=model)
    except Exception:  # unknown model: assume the conservative option
        supports_schema = False

    if supports_schema:
        return response_format

    logger.debug(
        "Model %r does not support response_format 'json_schema'; "
        "falling back to JSON mode ('json_object')",
        model,
    )
    return {"type": "json_object"}


_lite_llm._to_litellm_response_format = (
    _to_litellm_response_format_with_json_mode_fallback
)

#### END OF WORKAROUND

#### Start of workaround

# Every request logged a wall of
#   ERROR:opentelemetry.context:Failed to detach context
#   ValueError: <Token ...> was created in a different Context
# with a GeneratorExit traceback pointing into google/adk/flows/llm_flows/
# base_llm_flow.py. The runs still produced correct output, but the noise
# buried the real logs.
#
# Cause: an async generator does *not* close the iterator it is looping over
# when the loop exits early. ADK is careful about this and wraps every such
# loop in `Aclosing`, but two veadk passthrough generators use a bare
# `async for`:
#
#   veadk/agent.py       Agent._run_async_impl -> super()._run_async_impl(ctx)
#   veadk/runner.py      intercept_new_message's wrapper -> ADK Runner.run_async
#
# When the consumer stops early - which ADK does routinely, e.g. it breaks out
# of the flow loop right after `transfer_to_agent` - GeneratorExit is thrown
# into the veadk generator and its frame dies, dropping the last reference to
# the inner ADK generator without closing it. Python then finalizes that
# orphan through asyncio's async-generator hook, which runs `aclose()` in a
# brand-new task with a *fresh* contextvars Context. The OpenTelemetry spans
# ADK holds open across those yields try to `detach()` tokens that were
# attached in the original task's Context, and `ContextVar.reset` rejects
# them.
#
# Closing the inner generator deterministically, while still on the consuming
# task, fixes it at the source: the spans detach in the Context that attached
# them. Verified against google-adk 2.2.0 / veadk-python 1.1.2 with a mock
# model: a run that transfers to a sub-agent emits 4 of these errors before
# the patch and 0 after, with identical events and final output. Drop this
# block once veadk wraps both loops in `Aclosing` itself (it already does in
# veadk/a2a/remote_ve_agent.py).

import contextvars  # noqa: E402
import functools  # noqa: E402

import veadk.agent as _veadk_agent  # noqa: E402
import veadk.runner as _veadk_runner  # noqa: E402
from google.adk.utils.context_utils import Aclosing  # noqa: E402


async def _run_async_impl_closing(self, ctx):
    # Mirrors veadk.agent.Agent._run_async_impl, with `Aclosing` added.
    if self.runtime == "adk":
        async with Aclosing(
            super(_veadk_agent.Agent, self)._run_async_impl(ctx)
        ) as agen:
            async for event in agen:
                yield event
        return

    from veadk.runtime import get_runtime

    async with Aclosing(get_runtime(self.runtime).run_async(self, ctx)) as agen:
        async for event in agen:
            yield event


_veadk_agent.Agent._run_async_impl = _run_async_impl_closing


# The runner-side loop is buried inside a closure built by
# `intercept_new_message`, and its body also carries veadk's event logging.
# Rather than copy that logging (and let it drift on the next upgrade), keep
# veadk's wrapper as-is and hand it a `func` that records the generator it
# creates, so the outer wrapper can close it on the consuming task.
_inner_run_async_agens = contextvars.ContextVar(
    "veadk_runner_inner_agens", default=None
)
_original_intercept_new_message = _veadk_runner.intercept_new_message


def _intercept_new_message_with_closing(process_func):
    original_decorator = _original_intercept_new_message(process_func)

    def decorator(func):
        # `wraps` so the patched `run_async` keeps its original identity for
        # anything that introspects it.
        @functools.wraps(func)
        def _tracking_func(**kwargs):
            agen = func(**kwargs)
            box = _inner_run_async_agens.get()
            if box is not None:
                box.append(agen)
            return agen

        veadk_wrapper = original_decorator(_tracking_func)

        @functools.wraps(veadk_wrapper)
        async def wrapper(self, **kwargs):
            # One box per call. Async generators run in their caller's context,
            # so concurrent runs live on different tasks and cannot collide.
            box = []
            token = _inner_run_async_agens.set(box)
            try:
                async with Aclosing(veadk_wrapper(self, **kwargs)) as agen:
                    async for event in agen:
                        yield event
            finally:
                try:
                    _inner_run_async_agens.reset(token)
                except ValueError:
                    # Finalized in a different context than the one that set
                    # the token; the stale value dies with that context.
                    pass
                for inner in box:
                    await inner.aclose()

        return wrapper

    return decorator


# `Runner.__init__` calls this to build its per-instance `run_async`, so the
# patch has to be in place before any Runner is constructed.
_veadk_runner.intercept_new_message = _intercept_new_message_with_closing

#### END OF WORKAROUND
