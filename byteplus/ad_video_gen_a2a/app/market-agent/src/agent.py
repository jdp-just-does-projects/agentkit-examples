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

from market_agent.agent import agent  # type: ignore

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
    app_name="market_agent",
    agent=agent,  # type: ignore
    short_term_memory=ShortTermMemory(backend="local"),  # type: ignore
)
