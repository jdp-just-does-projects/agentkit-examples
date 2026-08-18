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

import os

# Load `.env` (project dir, then CWD; its values override the shell) before any
# veadk / agentkit import: veadk snapshots the environment at first import.
from consts import load_env_file

load_env_file()

from agentkit.apps import AgentkitAgentServerApp
from veadk.memory import ShortTermMemory

# Importing from `agent` (rather than `app` directly) applies the sys.path
# bootstrap and the LiteLlm/ArkLlm serialization and json-repair workarounds
# before the agent tree is built.
from agent import root_agent

short_term_memory = ShortTermMemory(backend="local")

agent_server_app = AgentkitAgentServerApp(
    agent=root_agent,
    short_term_memory=short_term_memory,
)

fastapi_app = getattr(agent_server_app, "app", None)
if fastapi_app is not None and os.getenv("DISABLE_OPENAPI", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}:
    openapi_url = getattr(fastapi_app, "openapi_url", "/openapi.json")
    docs_url = getattr(fastapi_app, "docs_url", "/docs")
    redoc_url = getattr(fastapi_app, "redoc_url", "/redoc")
    oauth2_redirect_url = getattr(
        fastapi_app, "swagger_ui_oauth2_redirect_url", "/docs/oauth2-redirect"
    )
    blocked_paths = {
        openapi_url,
        docs_url,
        redoc_url,
        oauth2_redirect_url,
    }

    if hasattr(fastapi_app, "router") and hasattr(fastapi_app.router, "routes"):
        fastapi_app.router.routes = [
            route
            for route in fastapi_app.router.routes
            if getattr(route, "path", None) not in blocked_paths
        ]

    fastapi_app.openapi_url = None
    fastapi_app.docs_url = None
    fastapi_app.redoc_url = None

if __name__ == "__main__":
    agent_server_app.run(host="0.0.0.0", port=8000)
