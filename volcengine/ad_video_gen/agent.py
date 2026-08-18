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
import logging
import os
import sys
from pathlib import Path

# Make this agent's own directory importable before anything local is imported.
# `veadk web` loads this file as the submodule `ad_video_gen.agent`, which only
# puts the *parent* directory on sys.path, so bare imports like `prompt` and
# `consts` would otherwise fail.
_AGENT_DIR = Path(__file__).resolve().parent
for _path in (str(_AGENT_DIR), str(_AGENT_DIR.parent)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Load `.env` and populate model defaults before any veadk (or agentkit, which
# may pull in veadk) import: veadk snapshots the environment at first import.
from consts import set_veadk_environment_variables

set_veadk_environment_variables()

from agentkit.apps import AgentkitAgentServerApp
from google.adk.models.lite_llm import LiteLlm
from google.genai import types
from veadk import Agent
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.models.ark_llm import ArkLlm
from veadk.tools.builtin_tools.image_generate import image_generate
from veadk.tools.builtin_tools.video_generate import video_generate

from prompt import PROMPT_AD_VIDEO_AGENT

# It is recommended to set the global logger via logging.basicConfig; default log level is INFO
logging.basicConfig(level=logging.INFO)
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
# JSONDecodeError. Still the case as of google-adk 2.6.2; recheck on upgrades.
# Fall back to json-repair, and log the raw payload so genuinely unrecoverable
# calls can be diagnosed instead of guessing at the model output.
import google.adk.models.lite_llm as _lite_llm
from json_repair import repair_json

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

root_agent = Agent(
    name="root_agent",
    model_name=os.getenv("MODEL_AGENT_NAME"),
    description="Generate ecommerce product marketing images and short videos.",
    instruction=PROMPT_AD_VIDEO_AGENT,
    tools=[
        image_generate,
        video_generate,
    ],
    generate_content_config=types.GenerateContentConfig(max_output_tokens=18000),
)


short_term_memory = ShortTermMemory(backend="local")

agent_server_app = AgentkitAgentServerApp(
    agent=root_agent,
    short_term_memory=short_term_memory,
)


if __name__ == "__main__":
    agent_server_app.run(host="0.0.0.0", port=8000)
