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

# Point veadk at BytePlus before anything imports it (veadk snapshots
# CLOUD_PROVIDER at first import; the workarounds module imports veadk).
from consts import set_veadk_environment_variables

set_veadk_environment_variables()

# Apply shared runtime patches (JSON repair for malformed tool calls, etc.)
# before any agent model is constructed.
import workarounds  # noqa: F401

from director_agent.agent import agent  # type: ignore

# Auto-continue guard. google-adk ends an agent's turn as soon as its model
# replies without a tool call. The director must always hand off to a
# sub-agent (transfer_to_agent), and the image / video sub-agents must actually
# call their generation tool before answering — a text-only reply at either
# point returns an incomplete result to the caller instead of the storyboard
# images / videos. The guard injects a `continue_pipeline` tool call whenever
# such a turn would end before the required tool has run. See pipeline_guard.py.
import pipeline_guard  # noqa: E402

pipeline_guard.install_by_name(
    agent,
    {
        "director_agent": {"required_tools": {"transfer_to_agent"}},
        "image_generate_agent": {"required_tools": {"image_generate"}},
        "video_generate_agent": {"required_tools": {"video_generate"}},
    },
)

# URL guard. Every asset URL in this pipeline is relayed *through* a model,
# and a ~500-character pre-signed TOS URL is occasionally retyped with a
# duplicated or dropped character - the download then fails with a 403 and the
# caller receives a non-JSON error string. The guard restores any URL the model
# mistyped from the authoritative value (tool output / the caller's message).
# See url_guard.py.
import url_guard  # noqa: E402

url_guard.install(agent)

from veadk.memory.short_term_memory import ShortTermMemory
from veadk.types import AgentRunConfig

# [required] instantiate the agent run configuration
agent_run_config = AgentRunConfig(
    app_name="director_agent",
    agent=agent,  # type: ignore
    short_term_memory=ShortTermMemory(backend="local"),  # type: ignore
)
