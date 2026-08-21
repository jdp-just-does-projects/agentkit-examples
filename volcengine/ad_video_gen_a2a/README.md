# Ad Video Generation Agent (A2A Multi-Agent) - E-commerce Marketing Videos

**IMPORTANT**: This demo was tested with Python 3.12, but other demos here require other versions of Python. We recommend installing and managing multiple versions of Python with [mise](https://mise.jdx.dev/getting-started.html).

This is a distributed multi-agent e-commerce marketing video generator based on Volcano Engine AgentKit and VeADK. Unlike the `ad_video_gen_seq` sample, which runs all agents inside one process, this sample splits the pipeline into **independently deployable services** that talk to each other over the **A2A (Agent-to-Agent) protocol**, each also exposing an MCP endpoint.

When given product information (a product image URL and/or a product link plus a text brief), it will:

- Parse the product assets and produce a marketing plan and video configuration script
- Design a 4-shot storyboard following the AIDA marketing model (Attention → Interest → Desire → Action)
- Generate candidate first-frame images per shot (Seedream 5.0 Pro), then score and select the best ones
- Generate candidate videos per shot from the selected first frames (Seedance 2.5), then score and select the best ones
- Compose the selected shot videos into one final video locally (moviepy/ffmpeg)

## Overview

Five services cooperate to run the pipeline. The multimedia agent is the root orchestrator: it receives user requests and dispatches each stage to a remote worker agent over A2A. Generated media URLs (TOS image links, Ark video links) are passed between the stages in full.

![Architecture](img/architecture.png)

<details>
<summary>Mermaid source</summary>

```mermaid
flowchart TB
    user(["User · app/main.py E2E driver or any ADK client<br/>product image URL and/or product link + text brief"])

    subgraph mm["multimedia-agent :8004 — AgentkitAgentServerApp"]
        direction TB
        mmroot["root_agent · deepseek-v4-pro-260425<br/>sub_agents = 4 × RemoteVeAgent (A2A clients)<br/>ShortTermMemory backend = local"]
    end

    subgraph market["market-agent :8000 — SequentialAgent"]
        direction TB
        mk1["market_agent<br/>tools: web_search · read_url_link<br/>Playwright page parsing · vision image filter"]
        mk2["format_agent → output_schema VideoConfig<br/>output_key: video_config"]
        mk1 --> mk2
    end

    subgraph director["director-agent :8001 — Agent with 3 sequential sub-agents"]
        direction TB
        dstory["story_sequential_agent<br/>storyboard_agent → story_format_agent<br/>output_key: shot_list"]
        dimage["image_agent<br/>image_generate_agent → image_format_agent<br/>output_key: image_list"]
        dvideo["video_agent<br/>video_generate_agent → video_format_agent<br/>output_key: video_list"]
        dstory --> dimage --> dvideo
    end

    subgraph evaluate["evaluate-agent :8002 — EvaluateAgent"]
        direction TB
        ev["tool: evaluate_media (G-Eval)<br/>scores every candidate image / video<br/>emits the raw tool result to the caller"]
    end

    subgraph release["release-agent :8003 — Agent → film_agent"]
        direction TB
        rel["film_generate_agent · tool: video_combine<br/>→ format_agent · output_key: video_url"]
    end

    ark["Volcano Engine Ark<br/>agents + formatters: deepseek-v4-pro-260425<br/>vision work (image understanding, G-Eval): doubao-seed-2-1-turbo-260628<br/>images: doubao-seedream-5-0-pro-260628 · videos: doubao-seedance-2-5-260628"]
    web["Volcano Engine web search + target product pages"]
    ffmpeg["Local moviepy / ffmpeg<br/>final composed video"]

    user -- "prompt" --> mmroot
    mmroot -- "1 · A2A: parse product, plan the video" --> mk1
    mmroot -- "2 · A2A: storyboard → images → clips" --> dstory
    mmroot -- "3 · A2A: score images, then score clips" --> ev
    mmroot -- "4 · A2A: compose the final video" --> rel
    mk2 -. "video_config" .-> mmroot
    dvideo -. "shot_list · image_list · video_list" .-> mmroot
    ev -. "scored_image_list / scored_video_list" .-> mmroot
    rel -. "video_url" .-> mmroot
    mmroot -- "final video URL" --> user

    mk1 --> web
    mk1 --> ark
    dimage --> ark
    dvideo --> ark
    ev --> ark
    rel --> ffmpeg

    classDef agent fill:#e7f0ff,stroke:#3b6fd4,color:#0d1b33
    classDef tool fill:#eafaf1,stroke:#2e9e6b,color:#08281a
    classDef ext fill:#fff4e5,stroke:#d98724,color:#3a2405
    classDef store fill:#f3ecfb,stroke:#8253c6,color:#22103a
    classDef actor fill:#eceef1,stroke:#7a828c,color:#1b1f24
    class mmroot,mk1,mk2,dstory,dimage,dvideo,ev,rel agent
    class ark,web,ffmpeg ext
    class user actor
    style mm fill:#f4f8ff,stroke:#3b6fd4,color:#0d1b33
    style market fill:#f7fbff,stroke:#5b8def,color:#0d1b33
    style director fill:#f7fbff,stroke:#5b8def,color:#0d1b33
    style evaluate fill:#f7fbff,stroke:#5b8def,color:#0d1b33
    style release fill:#f7fbff,stroke:#5b8def,color:#0d1b33
```

</details>

Key features include:

- **A2A microservice topology**: each worker is a standalone VeADK A2A server (`veadk.a2a.ve_a2a_server`) publishing an agent card at `/.well-known/agent-card.json`; the orchestrator connects with `RemoteVeAgent` clients
- **MCP on every worker**: each worker also mounts a streamable-HTTP MCP endpoint at `/mcp` (via FastMCP), so the same capabilities are callable as MCP tools
- **Web-based product parsing**: the market agent reads product links with a local Playwright browser (with SSRF/DoS guards) and filters product images with a vision model
- **Candidate generation and automatic evaluation**: every shot gets several candidate images/videos which are scored on aesthetics, image quality, and consistency with the reference image
- **Malformed-JSON resilience**: every service applies shared [`workarounds.py`](app/market-agent/src/workarounds.py) patches that repair malformed model output (tool-call arguments, structured output) with `json-repair` instead of aborting the run
- **English by Default**: Every agent in the pipeline (orchestrator and the four workers) is instructed to work in English by default — plans, storyboard scripts, image/video prompts, evaluation rationales, and replies. If your request is written in another language, the agents switch to that language for all of those outputs so the results are easy for you to review (see the `# Language` section in each `prompt.py`)

## Agent Capabilities

| Component | Description |
| --- | --- |
| **Multimedia Agent** | [`app/multimedia-agent/`](app/multimedia-agent/) - root orchestrator; plans the pipeline and calls the four workers over A2A |
| **Market Agent** | [`app/market-agent/`](app/market-agent/) - parses product images/links, produces the video configuration script |
| **Director Agent** | [`app/director-agent/`](app/director-agent/) - storyboard script, storyboard images, and storyboard videos |
| **Evaluate Agent** | [`app/evaluate-agent/`](app/evaluate-agent/) - scores storyboard images and videos with a vision model |
| **Release Agent** | [`app/release-agent/`](app/release-agent/) - composes the final video locally with moviepy |
| **E2E Driver** | [`app/main.py`](app/main.py) - runs the full 7-step pipeline against the local services |
| **Runtime Patches** | [`workarounds.py`](app/market-agent/src/workarounds.py) - shared JSON-repair and ADK patches (one copy per service) |
| **Auto-continue Guard** | [`pipeline_guard.py`](app/director-agent/src/pipeline_guard.py) - installed in the director, evaluate, and release services: if an agent ends its turn without its mandatory tool call (`transfer_to_agent`, `image_generate`, `video_generate`, `evaluate_media`, `video_combine`), the guard injects a `continue_pipeline` tool call so the service returns a complete result (one copy per service) |
| **Config Examples** | `app/<service>/config.yaml.example` - per-service model names, API bases, and service URLs |

## Quick Start

### Prerequisites

#### Volcano Engine Access Credentials

Make sure you have configured an IAM user, created a new Access Key / Secret Key pair, and that you have assigned the following permissions to the user:

- `AgentKitFullAccess` (AgentKit full access)
- `APMPlusServerFullAccess` (APMPlus full access)

In the web console, open the product search dropdown and search for "Ark" (方舟). Under "Model activation" make sure the following models are enabled:

- **Agent (text):** DeepSeek V4 Pro (model ID: `deepseek-v4-pro-260425`) — used by all five agent services
- **Vision tools:** Doubao Seed 2.1 Turbo (model ID: `doubao-seed-2-1-turbo-260628`) — used by the market agent's image-understanding/image-filter tools and the evaluate agent's media-scoring tool, which all consume images or videos
- **Images:** Seedream 5.0 Pro (model ID: `doubao-seedream-5-0-pro-260628`)
- **Video:** Seedance 2.5 (model ID: `doubao-seedance-2-5-260628`)

**Finally, from the "API Keys" page, create a new key and save it, we'll need it later on (see *Configure Environment Variables* below).**

#### TOS Bucket

The director agent uploads generated storyboard images to a TOS bucket. You can use the AgentKit platform bucket `agentkit-platform-{{your_account_id}}` (replace `{{your_account_id}}` with your Volcano Engine account ID) or any bucket the AK/SK pair can write to.

#### ffmpeg

Video composition uses `moviepy`, which needs a working `ffmpeg` on the machine that runs the release agent (e.g. `brew install ffmpeg` on macOS, `apt-get install ffmpeg` on Debian/Ubuntu).

#### Playwright Browser

The market agent parses product web pages with a headless Chromium browser. The browser itself is **not** installed by `uv sync` — it is a separate one-time download; see *Install the Playwright Browser (one time)* below.

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

### Install the Playwright Browser (one time)

`uv sync` installs the Playwright *Python package*, but not the browser binary it drives. **Before launching the agents for the first time, run this once** — the market agent fails at startup without it:

```bash
uv run playwright install chromium
```

On a fresh Linux machine, also install the browser's system libraries (needs `sudo` on most distributions):

```bash
uv run playwright install-deps chromium
```

This is a one-time, per-machine step: the browser is downloaded into a shared Playwright cache (`~/.cache/ms-playwright` on Linux, `~/Library/Caches/ms-playwright` on macOS), so you only need to repeat it on a new machine or after clearing that cache. If you have already installed Playwright browsers for another project, the command is a no-op.

### Configure Environment Variables

Set the following environment variables — either export them in your shell, or copy [`.env.example`](.env.example) to `.env` (in the project directory — shared by all services — next to a service's `config.yaml`, in its `src/` dir, or in the directory you launch from) and fill it in. `.env` is loaded automatically at startup (by each service's `consts.py`) and is optional; values in `.env` take precedence over variables exported in the shell, and anything missing from `.env` falls back to the shell environment. `.env` only applies to local runs — for cloud deploys pass values through `agentkit config --runtime_envs ...` (see below):

```bash
export MODEL_AGENT_API_KEY={{your_model_agent_api_key}} # Get from Volcano Engine Ark (方舟)
export VOLCENGINE_ACCESS_KEY={{your_access_key}}        # For TOS image upload (director) and web_search (market)
export VOLCENGINE_SECRET_KEY={{your_secret_key}}        # For TOS image upload (director) and web_search (market)
export DATABASE_TOS_BUCKET=agentkit-platform-{{your_account_id}}
```

Then create each service's `config.yaml` from its example (service URLs and model defaults are pre-filled; fill in `api_key`, or leave it empty if you exported `MODEL_AGENT_API_KEY` — environment variables take precedence over `config.yaml` keys):

```bash
for svc in market-agent director-agent evaluate-agent release-agent multimedia-agent; do
  cp app/$svc/config.yaml.example app/$svc/config.yaml
done
```

The model names can be overridden per service in its `config.yaml` or with environment variables (the values below are the defaults this sample is designed for):

```bash
export MODEL_AGENT_NAME=deepseek-v4-pro-260425
export MODEL_VISION_NAME=doubao-seed-2-1-turbo-260628   # market agent's image tools
export MODEL_EVALUATE_ITEM=doubao-seed-2-1-turbo-260628 # evaluate agent's scoring tool
export MODEL_IMAGE_NAME=doubao-seedream-5-0-pro-260628
export MODEL_VIDEO_NAME=doubao-seedance-2-5-260628
```

## Local Execution

If this is the first time you are running the sample on this machine, make sure you have run `uv run playwright install chromium` (see above) — the market agent needs the browser at startup.

Start the five services, each from its own directory (one terminal per service, or append `&` to background them). Start the four workers first — **the multimedia agent must start last**, because it fetches the workers' A2A agent cards at startup:

```bash
(cd app/market-agent/src    && uv run python -m uvicorn app:app    --host 127.0.0.1 --port 8000 --loop asyncio)
(cd app/director-agent/src  && uv run python -m uvicorn app:app    --host 127.0.0.1 --port 8001 --loop asyncio)
(cd app/evaluate-agent/src  && uv run python -m uvicorn app:app    --host 127.0.0.1 --port 8002 --loop asyncio)
(cd app/release-agent/src   && uv run python -m uvicorn app:app    --host 127.0.0.1 --port 8003 --loop asyncio)
(cd app/multimedia-agent/src && uv run python -m uvicorn server:app --host 127.0.0.1 --port 8004 --loop asyncio)
```

You can check that a worker is up by fetching its agent card, e.g. `curl http://127.0.0.1:8000/.well-known/agent-card.json`.

Then run the end-to-end pipeline driver:

```bash
uv run python app/main.py
```

The driver creates a session on the multimedia agent and walks through the 7 pipeline steps, saving every intermediate result under `tmp-json/local-<timestamp>/`.

### Example Prompts

The driver's default request is:

> Generate a promotional video (Product Showcase Video) for a waxberry drink. Product image: `https://ark-tutorial.tos-cn-beijing.volces.com/multimedia/%E6%9D%A8%E6%A2%85%E9%A5%AE%E6%96%99.jpg`

Edit `user_need` at the bottom of [`app/main.py`](app/main.py) to try your own product.

**Expected Behavior:**

1. **Video configuration** — the market agent parses the product image/link and returns a video configuration script (product info, selling points, video type)
2. **Storyboard script** — the director agent designs a 4-shot AIDA storyboard
3. **Storyboard images** — the director agent generates candidate first-frame images per shot
4. **Image evaluation** — the evaluate agent scores the images; the driver picks the best per shot
5. **Storyboard videos** — the director agent generates 4 candidate videos per shot from the selected first frames
6. **Video evaluation** — the evaluate agent scores the videos; the driver picks the best per shot
7. **Final video** — the release agent composes the selected shot videos into the final video (saved under `merged_videos/`)

## AgentKit Deployment

Each worker is an independently deployable AgentKit runtime: the deployable unit is the service's `src/` directory, whose `requirements.txt` describes its footprint and whose `app.py` (workers) or `server.py` (multimedia) is the entry point.

> **Note**: `config.yaml` is not deployed with the runtime — pass every setting the service needs (model names, API bases, service URLs) via `--runtime_envs`. This multi-runtime deployment follows the standard AgentKit pattern below but has been verified locally only; deploy one service at a time and test with `agentkit invoke` as you go.

**Step 0:** If you haven't installed agentkit yet, you can do it locally (inside the Python virtual environment) with:

```bash
uv pip install agentkit-sdk-python
```

**Step 1:** Deploy the four workers, one at a time, from each service's `src/` directory.

**Note**: We assume here that `MODEL_AGENT_API_KEY`, `VOLCENGINE_ACCESS_KEY`, `VOLCENGINE_SECRET_KEY`, and `DATABASE_TOS_BUCKET` are defined in your shell environment.

For example, for the director agent:

```bash
cd app/director-agent/src
uv run agentkit config \
--agent_name director_agent \
--entry_point 'app.py' \
--runtime_envs MODEL_AGENT_API_KEY=$MODEL_AGENT_API_KEY \
--runtime_envs MODEL_AGENT_NAME=deepseek-v4-pro-260425 \
--runtime_envs MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3/ \
--runtime_envs MODEL_IMAGE_NAME=doubao-seedream-5-0-pro-260628 \
--runtime_envs MODEL_VIDEO_NAME=doubao-seedance-2-5-260628 \
--runtime_envs VOLCENGINE_ACCESS_KEY=$VOLCENGINE_ACCESS_KEY \
--runtime_envs VOLCENGINE_SECRET_KEY=$VOLCENGINE_SECRET_KEY \
--runtime_envs DATABASE_TOS_BUCKET=$DATABASE_TOS_BUCKET \
--launch_type cloud
uv run agentkit launch
```

Repeat for `market_agent` (add nothing TOS-related, but keep the model and AK/SK variables), `evaluate_agent` (add `MODEL_EVALUATE_ITEM=doubao-seed-2-1-turbo-260628`), and `release_agent`. After each launch, note the runtime's public access domain from the [Volcano Engine AgentKit Console](https://console.volcengine.com/agentkit/region:agentkit+cn-beijing/runtime) (e.g. `https://xxxxx.apigateway-cn-beijing.volceapi.com`).

**Step 2:** Deploy the multimedia agent last, pointing it at the four workers' public URLs:

```bash
cd app/multimedia-agent/src
uv run agentkit config \
--agent_name multimedia_agent \
--entry_point 'server.py' \
--runtime_envs MODEL_AGENT_API_KEY=$MODEL_AGENT_API_KEY \
--runtime_envs MODEL_AGENT_NAME=deepseek-v4-pro-260425 \
--runtime_envs MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3/ \
--runtime_envs REMOTE_AGENT_MARKET_AGENT_URL={{market_agent_url}} \
--runtime_envs REMOTE_AGENT_DIRECTOR_AGENT_URL={{director_agent_url}} \
--runtime_envs REMOTE_AGENT_EVALUATE_AGENT_URL={{evaluate_agent_url}} \
--runtime_envs REMOTE_AGENT_RELEASE_AGENT_URL={{release_agent_url}} \
--launch_type cloud
uv run agentkit launch
```

### Test the Deployed Agent

You can directly use `agentkit invoke` (from the multimedia agent's directory) to trigger / debug the pipeline. The command is:

```bash
uv run agentkit invoke '{"prompt": "Generate a promotional video (Product Showcase Video) for a waxberry drink. Product image: https://ark-tutorial.tos-cn-beijing.volces.com/multimedia/%E6%9D%A8%E6%A2%85%E9%A5%AE%E6%96%99.jpg"}'
```

## Cleanup / Teardown

Local: stop the five uvicorn processes (Ctrl-C in each terminal, or `kill %1 %2 ...` if backgrounded) and remove the driver's output with `rm -rf tmp-json merged_videos`.

Cloud: remove each deployed runtime by running the following from the same service directory you deployed it from (multimedia agent first, then the workers):

```bash
uv run agentkit destroy
```

## FAQ

### Why does the sample use both DeepSeek V4 Pro and Doubao Seed 2.1 Turbo?

The agent LLMs never look at images directly — vision runs through dedicated tool-level model calls (the market agent's image understanding/filtering, and the evaluate agent's media scoring). So the agents use the text-only DeepSeek V4 Pro, while those tools default to the vision-capable Doubao Seed 2.1 Turbo (`MODEL_VISION_NAME` / `MODEL_EVALUATE_ITEM`).

### The market agent fails at startup with a Playwright error

Run `uv run playwright install chromium`, and on Linux also `uv run playwright install-deps chromium` (the browser needs system libraries such as `libatk`).

### The multimedia agent fails at startup with a connection error

It fetches the four workers' A2A agent cards at startup, so ports 8000-8003 must already be serving. Start it last.

### Where does the final video go?

The release agent composes the video locally with moviepy and saves it under `merged_videos/` in the repository; the returned `video_url` points at that file. The intermediate storyboard images are uploaded to your TOS bucket and returned as full URLs.

### Which ports must be free?

8000 (market), 8001 (director), 8002 (evaluate), 8003 (release), 8004 (multimedia).
