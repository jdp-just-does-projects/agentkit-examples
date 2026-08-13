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

import json
import json_repair
from typing import Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.events import Event
from google.adk.models import LlmResponse
from pydantic import ValidationError
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def fix_output_format(
    *,
    callback_context: CallbackContext,
    llm_response: LlmResponse,
    model_response_event: Optional[Event] = None,
) -> Optional[LlmResponse]:
    """
    Check whether the output format matches the expected schema and try to repair it.
    Possible cases:
    Case 1. (ok -> ok) No schema: return the original llm_response directly.
    Case 2. (ok -> ok) Schema present, output needs no repair and matches the schema: return llm_response. (The code replaces it, but effectively nothing changes.)
    Case 3. (bad -> bad) Schema present, output needs no repair but does not match the schema: return the original llm_response. Log it.
    Case 4. (bad -> bad) Schema present, output needs repair and the repair fails: return the original llm_response. Log it.
    Case 5. (**bad -> ok**) Schema present, output needs repair, repair succeeds and the result matches the schema: return the repaired llm_response.
    Case 6. (bad -> bad) Schema present, output needs repair, repair succeeds but the result does not match the schema: return the original llm_response. Log it.

    """
    agent = callback_context._invocation_context.agent
    user_id = callback_context._invocation_context.user_id
    session_id = callback_context._invocation_context.session.id
    invocation_id = callback_context.invocation_id
    output_schema = agent.output_schema

    message = f"[fix_output_format]: agent_name:{agent.name} user_id:{user_id} session_id:{session_id} invocation_id:{invocation_id}"
    fixed = False

    # 1. If there is no schema, just return directly
    if not output_schema:
        logger.debug(f"{message}\nNo output_schema, return original llm_response")
        return llm_response  # Case 1 (success)

    text = llm_response.content.parts[0].text
    logger.debug(f"{message}\nOriginal llm_response length: {len(text)}")

    # 2. Check whether the output format satisfies the output_schema
    try:
        output = json.loads(text)
    except json.JSONDecodeError:
        # Try to repair it
        try:
            output = json_repair.loads(text)
            if isinstance(output, list):
                output = output[0]
            fixed = True
        except Exception:
            logger.warning(
                f"{message}\nOutput format is not valid JSON, trying to `json_repair` but failed. Original output length: {len(text)}"
            )
            llm_response = llm_response_validate_error(
                llm_response,
                "ReleaseAgent output does not match the expected schema and could not be repaired; please retry.",
            )
            return llm_response  # Case 4 (failure)

    # 3. Check whether the output format satisfies the output_schema
    try:
        output_schema.model_validate(output)
        if fixed:
            llm_response.content.parts[0].text = json.dumps(output, ensure_ascii=False)
            fixed_text = json.dumps(output, ensure_ascii=False)
            logger.warning(
                f"{message}\nOutput format was not valid JSON, but `json_repair` success. Fixed output length: {len(fixed_text)}"
            )
        else:
            logger.debug(
                f"{message}\nOutput format is valid JSON and valid for output_schema. Original output length: {len(text)}"
            )
        return llm_response  # Case 2 & Case 5 (success)
    except ValidationError:
        if fixed:
            logger.warning(
                f"{message}\nOutput format was not valid JSON, `json_repair` success but the result is not valid for output_schema. Original output length: {len(text)}"
            )
        else:
            logger.warning(
                f"{message}\nOutput format is valid JSON but not valid for output_schema. Original output length: {len(text)}"
            )
        llm_response = llm_response_validate_error(
            llm_response,
            "ReleaseAgent output does not match the expected schema; please retry.",
        )
        return llm_response  # Case 6 & Case 3 (failure)


def llm_response_validate_error(llm_response: LlmResponse, reason: str) -> LlmResponse:
    llm_response.content.parts[0].text = json.dumps(
        {"status": {"success": False, "message": reason}}
    )
    return llm_response
