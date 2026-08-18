# Sandbox Demo - Cloud Coding Agent

**IMPORTANT**: This demo was tested with Python 3.12, but other demos here require other versions of Python. We recommend installing and managing multiple versions of Python with [mise](https://mise.jdx.dev/getting-started.html).

This is a "Cloud Coding Agent" based on Volcano Engine AgentKit. It showcases the **AgentKit AIO Sandbox**: a secure, isolated cloud execution environment with a shell, file system, Python/Node.js runtimes, and outbound network access.

When given a web coding task (e.g. *"build a landing page with a countdown timer"*), the agent will:

- Plan the project and scaffold it **inside the AIO Sandbox** (never on the machine the agent runs on)
- Write every source file in the sandbox using shell commands
- **Test the code inside the sandbox**: syntax checks, unit tests, and actually serving the app and verifying it with `curl`
- Zip the finished project inside the sandbox
- Upload the zip **directly from the sandbox to TOS** using a presigned URL
- Return a signed TOS download link for the completed, tested code

## Overview

### Core Features

This use case demonstrates how to build an agent around the AgentKit sandbox with the following capabilities:

- **Isolated Code Execution**: All code is written and executed in a remote AIO Sandbox session via the veadk built-in `run_code` tool, which drives the sandbox through the AgentKit `InvokeTool` API (`ExecBash` for shell commands, `RunCode` for Python kernels).
- **Stateful Sandbox Sessions**: Sandbox sessions persist between tool calls, so the agent can scaffold, test, fix, and package a project across many steps — and iterate on the same project in follow-up turns.
- **Real Testing, Not Claims**: The agent starts a web server inside the sandbox, curls it, and asserts on the response before declaring the task done.
- **Credential-free Artifact Delivery**: The agent runtime generates a presigned TOS PUT/GET URL pair; the sandbox pushes the zip to TOS with plain `curl -T`. Cloud credentials never enter the sandbox.

The flow looks like this:

```text
User Request ("build me a web page that ...")
    ↓
AgentKit Runtime
    ↓
Cloud Coding Agent (sandbox_web_coder)
    ├── run_code Tool ──────────► AgentKit AIO Sandbox
    │                                ├── write source files (bash heredocs)
    │                                ├── syntax checks + unit tests
    │                                ├── serve app + curl verification
    │                                ├── zip project
    │                                └── curl -T project.zip <presigned PUT URL> ──► TOS
    └── TOS Presign Tool (generates the presigned PUT/GET URL pair)
    ↓
User receives a signed TOS download link to the tested code
```

## Agent Capabilities

| Component | Description |
| --- | --- |
| **Agent Service** | [`agent.py`](agent.py) - Main application |
| **Agent Configuration** | [`agent.yaml`](agent.yaml) - Model settings, system instructions, and tool list |
| **Sandbox Execution** | `veadk.tools.builtin_tools.run_code` - Runs shell commands and code in the AIO Sandbox |
| **Custom Tools** | [`tool/tos_presign.py`](tool/tos_presign.py) - Presigned TOS upload/download URL pair generator |
| **Short-term Memory** | Session context maintenance to preserve conversational continuity |

## Quick Start

### Prerequisites

#### Volcano Engine Access Credentials

Make sure you have configured an IAM user, created a new Access Key / Secret Key pair, and that you have assigned the following permissions to the user:

- `AgentKitFullAccess` (AgentKit full access)
- `TOSFullAccess` (TOS full access, for presigned URL generation)

In the web console, open the product search dropdown and search for "Ark" (方舟). Under "Model activation" make sure the following model is enabled:

- **Text:** DeepSeek V4 Pro (model ID: `deepseek-v4-pro-260425`)

**Finally, from the "API Keys" page, create a new key and save it, we'll need it later on (see *Configure Environment Variables* below).**

#### Create an AIO Sandbox Tool

The agent needs an **All-in-one (AIO) sandbox tool** in your AgentKit account. You can create one from the [AgentKit console](https://console.volcengine.com/agentkit/region:agentkit+cn-beijing/tool) (Tools → Create → AIO Sandbox), or programmatically.

After the tool is created, its tool ID (`t-...`) **must be exported as `AGENTKIT_TOOL_ID`** in the shell where you run the agent — the `run_code` tool resolves the sandbox from that variable at call time. The snippet below creates the tool and exports the variable in one step:

```bash
export AGENTKIT_TOOL_ID=$(uv run python - <<'EOF'
import sys
import uuid
from agentkit.sdk.tools.client import AgentkitToolsClient
from agentkit.sdk.tools import types as tt

resp = AgentkitToolsClient().create_tool(tt.CreateToolRequest(
    Name="sandbox_demo_aio",
    ToolType="All-in-one",
    Description="AIO sandbox for the sandbox_demo web coding agent",
    EnableSnapshot=True,
    AuthorizerConfiguration=tt.AuthorizerForCreateTool(
        KeyAuth=tt.AuthorizerKeyAuthForCreateTool(
            ApiKeyName=f"apikey_{uuid.uuid4().hex[:8]}",
            ApiKeyLocation="Header",
        )
    ),
))
print("Created sandbox tool:", resp.tool_id, file=sys.stderr)
# Only the tool ID goes to stdout, so the shell can capture it
print(resp.tool_id)
EOF
)
echo "AGENTKIT_TOOL_ID=$AGENTKIT_TOOL_ID"
```

`export` only affects the current shell session — when you open a new terminal, re-export the same tool ID (there is no need to create a new tool). You may want to add the `export AGENTKIT_TOOL_ID=t-...` line to your shell profile.

> **Snapshots** (`EnableSnapshot=True`): when a sandbox session's TTL expires, AgentKit takes a snapshot instead of discarding the instance; the next access to the same session transparently recreates the instance from the snapshot. For this agent that means a user can come back to a conversation hours later and the project files in `/tmp/workspace/` are still there. Snapshots can only be enabled at tool creation time — there is no update path, so if you have a non-snapshot tool you must recreate it.

> **Note**: If you already have a sandbox tool but invocations fail with `SandboxCapabilityNotSupported: The current sandbox image does not support operation ExecBash`, your tool was created from an older sandbox image. Create a new tool as shown above.

### Install Dependencies

*We recommend using uv to manage Python dependencies*

Once UV is installed, set up with:

```bash
uv sync
```

If you are in China and have connectivity issues, you can use this command instead:

```bash
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### Configure Environment Variables

Set the following environment variables — either export them in your shell, or copy [`.env.example`](.env.example) to `.env` (in the project directory or in the directory you launch from) and fill it in. `.env` is loaded automatically at startup (see [`consts.py`](consts.py)) and is optional; values in `.env` take precedence over variables exported in the shell, and anything missing from `.env` falls back to the shell environment. `.env` only applies to local runs — for cloud deploys pass values through `agentkit config --runtime_envs ...` (see below):

```bash
export VOLCENGINE_ACCESS_KEY={your_ak}
export VOLCENGINE_SECRET_KEY={your_sk}
export DATABASE_TOS_BUCKET=agentkit-platform-{{your_account_id}}
export MODEL_AGENT_API_KEY={{your_model_agent_api_key}} # Get from Volcano Engine Ark (方舟), required for local debugging
export AGENTKIT_TOOL_ID={{your_sandbox_tool_id}}        # Already set if you used the creation snippet above in this shell
```

**TOS Bucket Configuration:**

- **Default bucket**: `agentkit-platform-{{your_account_id}}`
  - Where `{{your_account_id}}` needs to be replaced with your Volcano Engine account ID
  - Example: `DATABASE_TOS_BUCKET=agentkit-platform-12345678901234567890`
- **If you need to customize, you can modify the `bucket_name` parameter in [`tool/tos_presign.py`](tool/tos_presign.py) or pass it in during the tool call.**

## Local Execution

The simplest way to debug locally is with `veadk web`:

> `veadk web` is a web service based on FastAPI for debugging Agent applications. When you run this command, it starts a web server that loads and runs your agentkit agent code, while also providing a chat interface where you can interact with the agent. In the sidebar or a specific panel of the interface, you can view the details of the agent's execution, including the Thought Process, Tool calls, and model input/output.

Running it from within the project directory is straightforward:

```bash
uv run veadk web
```

Visit `http://localhost:8000` in your browser, select the `sandbox_demo` agent, enter a prompt, and click "Send".

### Example Prompts

- **Static page**: "Build a single-page countdown timer that counts down to New Year 2027"
- **Small game**: "Write a browser-based memory card matching game in plain HTML/CSS/JS"
- **API service**: "Write a Flask JSON API for a todo list, with unit tests"
- **Utility page**: "Build a markdown previewer web page with live rendering"
- **Follow-up iteration**: "Now add a dark mode toggle to it" (the agent reuses the same sandbox project)

**Expected Behavior:**

1. The agent restates the task and picks a project layout
2. Scaffolds and writes all files under `/tmp/workspace/<slug>/` in the AIO Sandbox
3. Runs syntax checks and tests, serves the app inside the sandbox, and curl-verifies it (you will see the real command output in the tool call results)
4. Zips the project and uploads it to TOS from inside the sandbox via a presigned URL
5. Returns a signed TOS download link, valid for 7 days

## AgentKit Deployment

### Deploy to Volcano Engine AgentKit Runtime

**Step 0:** If you haven't installed agentkit yet, you can do it locally (inside the Python virtual environment) with:

```bash
uv pip install agentkit-sdk-python
```

**Step 1:** Make sure you are in the current directory (`sandbox_demo`), then configure AgentKit:

**Note**: We assume here that `DATABASE_TOS_BUCKET`, `MODEL_AGENT_API_KEY`, and `AGENTKIT_TOOL_ID` are defined in your shell environment

```bash
uv run agentkit config \
--agent_name sandbox_web_coder \
--entry_point 'agent.py' \
--runtime_envs DATABASE_TOS_BUCKET=$DATABASE_TOS_BUCKET \
--runtime_envs MODEL_AGENT_API_KEY=$MODEL_AGENT_API_KEY \
--runtime_envs AGENTKIT_TOOL_ID=$AGENTKIT_TOOL_ID \
--launch_type cloud
```

**Step 2:** Deploy the runtime:

```bash
uv run agentkit launch
```

### Test the Deployed Agent

After successful deployment:

1. Visit the [Volcano Engine AgentKit Console](https://console.volcengine.com/agentkit/region:agentkit+cn-beijing/runtime)
2. Click **Runtime** to view the deployed agent `sandbox_web_coder`
3. Get the public access domain name (e.g., `https://xxxxx.apigateway-cn-beijing.volceapi.com`) and API Key

#### Interact via the chat UI

The agent runtime includes a simple web UI (chat window) where you can interact directly with the agent.

#### Interact via the command line (CLI)

You can directly use `agentkit invoke` to trigger / debug the agent. The command is:

```bash
uv run agentkit invoke '{"prompt": "Build a single-page countdown timer that counts down to New Year 2027"}'
```

## Cleanup / Teardown

You can remove your deployed AgentKit runtime with:

```bash
uv run agentkit destroy
```

To also remove the AIO sandbox tool:

```bash
uv run agentkit sandbox delete --tool-id {{your_sandbox_tool_id}}
```

## Debugging tips

Having trouble understanding why AgentKit isn't doing what you expect? Try adding these environment variables to enable additional debug output:

```bash
export AGENTKIT_LOG_CONSOLE=true
export AGENTKIT_LOG_LEVEL=DEBUG
```

**`ValueError: The environment variable AGENTKIT_TOOL_ID not exists` when the agent calls run_code:** the shell running the agent has no `AGENTKIT_TOOL_ID` exported. Export the tool ID of your AIO sandbox tool (see *Create an AIO Sandbox Tool* above) and restart the agent.

**401 `AuthenticationError: The API key doesn't exist` on model calls:** check whether your shell exports `CLOUD_PROVIDER=byteplus` (e.g. left over from running the BytePlus demos). That variable makes veadk default every model endpoint to BytePlus (`ark.ap-southeast.bytepluses.com`), where a Volcano Engine Ark key is invalid. This demo pins `model_api_base` in [`agent.yaml`](agent.yaml) so the agent model is immune, but other veadk defaults (image/video models, tool endpoints) still switch — when working with the Volcano Engine demos, run `unset CLOUD_PROVIDER AGENTKIT_CLOUD_PROVIDER` first.

## How the sandbox is used (implementation notes)

- The veadk built-in tool [`run_code`](https://github.com/volcengine/veadk-python) resolves the sandbox tool ID from `AGENTKIT_TOOL_ID` (or `AGENTKIT_TOOL_ID_SCRIPT`) and calls the AgentKit `InvokeTool` API with operation `ExecBash` (for `language: "bash"`) or `RunCode` (for `language: "python3"`, a Jupyter kernel).
- The sandbox session ID is derived from the agent name + user ID + ADK session ID, so each chat session gets its own isolated sandbox session, and files persist across tool calls within a session (session TTL is controlled by `AGENTKIT_TOOL_TTL`, default 1800s).
- The sandbox has outbound internet access but no cloud credentials. To get artifacts out, [`tool/tos_presign.py`](tool/tos_presign.py) generates a presigned PUT/GET URL pair on the agent side; the sandbox uploads with `curl -T` and the user receives the GET link.

## Known issues

- The first `run_code` call in a session may take noticeably longer than subsequent ones, since AgentKit provisions a fresh sandbox instance on demand (or restores it from a snapshot).
- Sandbox sessions expire after the TTL (default 30 minutes of inactivity, controlled by `AGENTKIT_TOOL_TTL`). With `EnableSnapshot=True` (as configured above) the session state is snapshotted on expiry and restored transparently on the next call, so project files survive. If you created the tool *without* snapshots, the files are gone after expiry and the agent must scaffold again.
