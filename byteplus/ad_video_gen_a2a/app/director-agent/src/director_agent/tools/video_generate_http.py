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

import asyncio
import hashlib
import json
import re
import traceback
from typing import Dict
import aiohttp

from google.adk.tools import ToolContext
from opentelemetry import trace
from opentelemetry.trace import Span

from veadk.config import getenv, settings
from veadk.consts import DEFAULT_VIDEO_MODEL_API_BASE, DEFAULT_VIDEO_MODEL_NAME
from veadk.utils.logger import get_logger
from veadk.version import VERSION

logger = get_logger(__name__)


# Seedance rejects an explicit aspect ratio on a frame-guided clip: for
# first-frame (or first+last-frame) generation the output ratio follows the
# first-frame image, so the only value the API accepts is `adaptive`. Anything
# else comes back as `InvalidParameter.TaskTypeConstraint`, the task fails, and
# the agent - which is told only that the video count is short - retries the
# same prompt forever. The aspect ratio is a text command the model writes into
# the prompt, so normalize it here instead of relying on every prompt being
# right.
_RATIO_COMMAND_RE = re.compile(r"--(?:rt|ratio)(?:\s+|=)\S+")


def _force_adaptive_ratio(prompt: str) -> str:
    """Force `--rt adaptive` on prompts for first/last-frame guided clips."""
    if _RATIO_COMMAND_RE.search(prompt):
        fixed = _RATIO_COMMAND_RE.sub("--rt adaptive", prompt)
        if fixed != prompt:
            logger.debug(
                "Rewrote the aspect-ratio text command to `--rt adaptive`: a "
                "frame-guided clip inherits its ratio from the first frame."
            )
        return fixed
    return f"{prompt.rstrip()} --rt adaptive"


# Ark answers a rejected request with an error code in the response body, and
# some of those codes are verdicts on *what the request contains* rather than on
# how it was written. The one this pipeline hits routinely is
# `InputImageSensitiveContentDetected.PrivacyInformation` - "the input image may
# contain real person" - because the image stage happily draws photorealistic
# faces that the video stage then refuses as a likeness risk. No edit to the
# request body fixes that, so resubmitting can only fail the same way; the
# caller has to change the content or give up. Everything else (a bad parameter,
# a transient 5xx) stays retryable.
_TERMINAL_ERROR_CODE_PREFIXES = (
    "InputImageSensitiveContentDetected",
    "InputTextSensitiveContentDetected",
    "OutputImageSensitiveContentDetected",
    "OutputVideoSensitiveContentDetected",
    "SensitiveContentDetected",
)


class VideoTaskError(Exception):
    """An Ark failure that carries the code and message the API actually sent.

    `aiohttp`'s `raise_for_status()` throws the response body away, so the only
    thing that used to reach the agent was ``400, message='Bad Request',
    url=...``. That names no cause, which left the model nothing to act on but a
    verbatim resubmit of the same doomed parameters.
    """

    def __init__(self, code: str, message: str, status: int | None = None):
        self.code = code
        self.message = message
        self.status = status
        self.terminal = any(
            code.startswith(prefix) for prefix in _TERMINAL_ERROR_CODE_PREFIXES
        )
        detail = f"{code}: {message}" if code else message
        super().__init__(f"HTTP {status} {detail}" if status else detail)


def _error_from_payload(payload: object, status: int | None = None) -> VideoTaskError:
    """Build a `VideoTaskError` from an Ark ``{"error": {...}}`` payload."""
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return VideoTaskError(
            str(error.get("code") or ""), str(error.get("message") or ""), status
        )
    return VideoTaskError("", str(error if error is not None else payload), status)


def _error_from_body(body: str, status: int) -> VideoTaskError:
    """Build a `VideoTaskError` from a raw HTTP body, which may not be JSON."""
    try:
        payload = json.loads(body)
    except ValueError:
        return VideoTaskError("", (body or "").strip()[:1000], status)
    return _error_from_payload(payload, status)


def _rejection_key(prompt: str, first_frame, last_frame) -> str:
    """Session-state key identifying one exact generation request."""
    digest = hashlib.sha256(
        json.dumps([prompt, first_frame, last_frame], ensure_ascii=False).encode()
    ).hexdigest()[:32]
    return f"_video_generate_rejected_{digest}"


async def generate(prompt, first_frame_image=None, last_frame_image=None):
    """
    Generate a video using HTTP requests
    """
    api_key = getenv(
        "MODEL_VIDEO_API_KEY", getenv("MODEL_AGENT_API_KEY", settings.model.api_key)
    )
    base_url = getenv("MODEL_VIDEO_API_BASE", DEFAULT_VIDEO_MODEL_API_BASE)
    model = getenv("MODEL_VIDEO_NAME", DEFAULT_VIDEO_MODEL_NAME)

    # Build the content array
    if first_frame_image or last_frame_image:
        prompt = _force_adaptive_ratio(prompt)

    prompt_with_media = (
        "(Very light incidental action sounds are allowed, but no human voice, "
        "no background music, no sound effects, no narration, no commentary.) "
        f"{prompt}"
    )
    content = [{"type": "text", "text": prompt_with_media}]

    if first_frame_image and last_frame_image:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": first_frame_image},
                "role": "first_frame",
            }
        )
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": last_frame_image},
                "role": "last_frame",
            }
        )
    elif first_frame_image:
        content.append({"type": "image_url", "image_url": {"url": first_frame_image}})

    # Build the request body
    request_body = {
        "model": model,
        "content": content,
        # "generate_audio": True,       # for seedance 1.5 pro only
        # Duration is controlled via the `--dur` text command in the prompt
        # (request-body parameters would override it). Seedance 2.5: 4-30 s.
    }

    # Build headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "veadk-source": "veadk",
        "veadk-version": VERSION,
        "User-Agent": f"VeADK/{VERSION}",
        "X-Client-Request-Id": getenv("MODEL_AGENT_CLIENT_REQ_ID", f"veadk/{VERSION}"),
    }

    # Make the POST request
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{base_url.rstrip('/')}/contents/generations/tasks",
                json=request_body,
                headers=headers,
            ) as response:
                # Read the body before deciding what to do with the
                # status: `raise_for_status()` discards it, and the body is the
                # only place the API says *why* it rejected the request.
                body = await response.text()
                if response.status >= 400:
                    raise _error_from_body(body, response.status)
                return json.loads(body)
        except Exception:
            logger.error(f"Error in generate: {traceback.format_exc()}")
            raise


async def video_generate(
    params: list, tool_context: ToolContext, batch_size: int = 32
) -> Dict:
    """
    Generate videos in **batch** from text prompts, optionally guided by a first/last frame,
    and fine-tuned via *model text commands* (a.k.a. `parameters` appended to the prompt).

    This API creates video-generation tasks. Each item in `params` describes a single video.
    The function submits all items in one call and returns task metadata for tracking.

    Args:
        params (list[dict]):
            A list of video generation requests. Each item supports the fields below.
            Required per item:
                - video_name (str):
                    Name/identifier of the output video file.

                - prompt (str):
                    Text describing the video to generate. Supports English and Chinese.
                    You may append **model text commands** after the prompt to control resolution,
                    aspect ratio, duration, fps, watermark, seed, camera lock, etc.
                    Format: `... --rs <resolution> --rt <ratio> --dur <seconds> --fps <fps> --wm <bool> --seed <int> --cf <bool>`
                    Example:
                        "A kitten rides a skateboard through the park. --rs 720p --rt 16:9 --dur 5 --fps 24 --wm true --seed 11 --cf false"

            Optional per item:
                - first_frame (str | None):
                    URL or Base64 string (data URL) for the **first frame** (role = `first_frame`).
                    Use when you want the clip to start from a specific image.

                - last_frame (str | None):
                    URL or Base64 string (data URL) for the **last frame** (role = `last_frame`).
                    Use when you want the clip to end on a specific image.

            Notes on first/last frame:
                * When both frames are provided, **match width/height** to avoid cropping; if they differ,
                  the tail frame may be auto-cropped to fit.
                * If you only need one guided frame, provide either `first_frame` or `last_frame` (not both).

            Image input constraints (for first/last frame):
                - Formats: jpeg, png, webp, bmp, tiff, gif
                - Aspect ratio (width:height): 0.4–2.5
                - Width/Height (px): 300–6000
                - Size: < 30 MB
                - Base64 data URL example: `data:image/png;base64,<BASE64>`

    Model text commands (append after the prompt; unsupported keys are ignored by some models):
        --rs / --resolution <value>       Video resolution. Common values: 480p, 720p, 1080p.
                                          Default depends on the model (e.g., dreamina-seedance-2-5: 1080p,
                                          some others default 720p).

        --rt / --ratio <value>            Aspect ratio. Typical: 16:9 (default), 9:16, 4:3, 3:4, 1:1, 2:1, 21:9.
                                          Some models support `keep_ratio` (keep source image ratio) or `adaptive`
                                          (auto choose suitable ratio).
                                          IMPORTANT: when `first_frame` (or `first_frame` + `last_frame`) is given,
                                          the output ratio follows the first-frame image and the API accepts only
                                          `--rt adaptive` - any other value fails the task with
                                          `InvalidParameter.TaskTypeConstraint`. This tool rewrites the command to
                                          `--rt adaptive` for you in that case, so choose the clip's aspect ratio
                                          when you generate the first-frame image, not here.

        --dur / --duration <seconds>      Clip length in seconds. Seedance 2.5 supports **4–30 s** (default 5).
                                          When clips will be stitched into a longer final video, prefer
                                          longer clips (up to 30 s) over a larger number of short clips.

        --fps / --framespersecond <int>   Frame rate. Common: 16 or 24 (model-dependent).

        --wm / --watermark <true|false>   Whether to add watermark. Default: **false** (per doc).

        --seed <int>                      Random seed in [-1, 2^32-1]. Default **-1** = auto seed.
                                          Same seed may yield similar (not guaranteed identical) results across runs.

        --cf / --camerafixed <true|false> Lock camera movement. Some models support this flag.
                                          true: try to keep camera fixed; false: allow movement. Default: **false**.

    Returns:
        Dict:
            API response containing task creation results for each input item. A typical shape is:
            {
                "status": "success",
                "success_list": [{"video_name": "video_url"}],
                "error_list": [],
                "errors": {"video_name": "why this one failed"},
                "permanent_failures": ["video_name"]
            }

            `permanent_failures` lists the items the API rejected for their
            content (a moderation verdict on the prompt or the first frame).
            Those cannot be produced from the parameters given, so do not
            resubmit them unchanged - change the content or drop them.

    Constraints & Tips:
        - Keep the prompt concise and focused (recommended ≤ 500 words); too many details may distract the model.
        - If using first/last frames, ensure their **aspect ratio matches** your chosen `--rt` to minimize cropping.
        - If you must reproduce results, specify an explicit `--seed`.
        - Unsupported parameters are ignored silently or may cause validation errors (model-specific).

    Minimal examples:
        1) Text-only batch of two clips at 720p, 16:9, 24 fps:
            params = [
                {
                    "video_name": "cat_park.mp4",
                    "prompt": "A kitten rides a skateboard through the park. --rs 720p --rt 16:9 --fps 24 --wm false"
                },
                {
                    "video_name": "city_night.mp4",
                    "prompt": "Time-lapse style city under neon lights. --rs 720p --rt 16:9 --fps 24 --seed 7"
                },
            ]

        2) With guided first/last frame (square, 6 s, camera fixed):
            params = [
                {
                    "video_name": "logo_reveal.mp4",
                    "first_frame": "https://cdn.example.com/brand/logo_start.png",
                    "last_frame": "https://cdn.example.com/brand/logo_end.png",
                    "prompt": "The brand logo transforms from line art to full color. --rs 1080p --rt 1:1 --dur 6 --fps 24 --cf true"
                }
            ]
    """
    success_list = []
    error_list = []
    errors: Dict[str, str] = {}  # video_name -> why it failed, surfaced to the agent
    permanent_failures: list[str] = []  # rejected on content: retrying cannot help
    api_key = getenv(
        "MODEL_VIDEO_API_KEY", getenv("MODEL_AGENT_API_KEY", settings.model.api_key)
    )
    base_url = getenv("MODEL_VIDEO_API_BASE", DEFAULT_VIDEO_MODEL_API_BASE)
    model = getenv("MODEL_VIDEO_NAME", DEFAULT_VIDEO_MODEL_NAME)

    logger.debug(f"Using model: {model}")
    logger.debug(f"video_generate params: {params}")

    for start_idx in range(0, len(params), batch_size):
        batch = params[start_idx : start_idx + batch_size]
        logger.debug(f"video_generate batch {start_idx // batch_size}: {batch}")

        task_dict = {}  # task_id: video_name
        task_keys = {}  # task_id: rejection key, to record a terminal failure
        tracer = trace.get_tracer("gcp.vertex.agent")
        with tracer.start_as_current_span("call_llm") as span:
            input_part = {"role": "user"}
            output_part = {"message.role": "model"}
            total_tokens = 0

            for idx, item in enumerate(batch):
                input_part[f"parts.{idx}.type"] = "text"
                input_part[f"parts.{idx}.text"] = json.dumps(item, ensure_ascii=False)

                video_name = item["video_name"]
                prompt = item["prompt"]
                first_frame = item.get("first_frame", None)
                last_frame = item.get("last_frame", None)

                # A content rejection is a property of the request itself, so
                # a repeat of one already refused in this session cannot
                # succeed. Answer it from the record rather than paying for the
                # round trip - and the polling wait behind it - all over again.
                rejection_key = _rejection_key(prompt, first_frame, last_frame)
                previous = tool_context.state.get(rejection_key)
                if previous:
                    logger.warning(
                        f"Skipping {video_name}: this exact request was already "
                        f"rejected in this session ({previous})"
                    )
                    error_list.append(video_name)
                    errors[video_name] = str(previous)
                    permanent_failures.append(video_name)
                    continue

                try:
                    # Create video generation task
                    response = await generate(prompt, first_frame, last_frame)
                    task_id = response["id"]
                    task_dict[task_id] = video_name
                    task_keys[task_id] = rejection_key
                    logger.debug(f"Created task {task_id} for video {video_name}")
                except Exception as e:
                    logger.error(f"Error creating task for {video_name}: {e}")
                    error_list.append(video_name)
                    errors[video_name] = str(e)
                    if isinstance(e, VideoTaskError) and e.terminal:
                        permanent_failures.append(video_name)
                        tool_context.state[rejection_key] = str(e)
                    continue

            logger.debug("Begin querying video_generate task status...")

            while True:
                task_list = list(task_dict.keys())
                if len(task_list) == 0:
                    break

                # Check each task status
                async with aiohttp.ClientSession() as session:
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "veadk-source": "veadk",
                        "veadk-version": VERSION,
                        "User-Agent": f"VeADK/{VERSION}",
                        "X-Client-Request-Id": getenv(
                            "MODEL_AGENT_CLIENT_REQ_ID", f"veadk/{VERSION}"
                        ),
                    }

                    for task_id in task_list:
                        try:
                            async with session.get(
                                f"{base_url.rstrip('/')}/contents/generations/tasks/{task_id}",
                                headers=headers,
                            ) as response:
                                response.raise_for_status()
                                result = await response.json()
                                status = result["status"]

                                if status == "succeeded":
                                    video_name = task_dict[task_id]
                                    video_url = result["content"]["video_url"]
                                    logger.debug(
                                        f"{video_name} video_generate succeeded. Video URL: {video_url}"
                                    )
                                    tool_context.state[f"{video_name}_video_url"] = (
                                        video_url
                                    )

                                    success_list.append({video_name: video_url})
                                    task_dict.pop(task_id, None)

                                elif status == "failed":
                                    video_name = task_dict[task_id]
                                    failure = _error_from_payload(result)
                                    logger.error(
                                        f"{video_name} video_generate failed. Error: {failure}"
                                    )
                                    error_list.append(video_name)
                                    errors[video_name] = str(failure)
                                    if failure.terminal:
                                        permanent_failures.append(video_name)
                                        tool_context.state[task_keys[task_id]] = str(
                                            failure
                                        )
                                    task_dict.pop(task_id, None)

                                else:
                                    logger.debug(
                                        f"{task_dict[task_id]} video_generate current status: {status}, Retrying after 10 seconds..."
                                    )
                        except Exception as e:
                            logger.error(
                                f"Error checking task status for {task_id}: {e}"
                            )
                            # Keep the task in the dict to retry later

                # Wait before next polling
                await asyncio.sleep(10)

            # Add span attributes
            add_span_attributes(
                span,
                tool_context,
                input_part=input_part,
                output_part=output_part,
                output_tokens=total_tokens,
                total_tokens=total_tokens,
                request_model=model,
                response_model=model,
            )

    if len(success_list) == 0:
        logger.debug(
            f"video_generate success_list: {success_list}\nerror_list: {error_list}"
        )
        return {
            "status": "error",
            "success_list": success_list,
            "error_list": error_list,
            "errors": errors,
            "permanent_failures": permanent_failures,
        }
    else:
        logger.debug(
            f"video_generate success_list: {success_list}\nerror_list: {error_list}"
        )
        return {
            "status": "success",
            "success_list": success_list,
            "error_list": error_list,
            "errors": errors,
            "permanent_failures": permanent_failures,
        }


def add_span_attributes(
    span: Span,
    tool_context: ToolContext,
    input_part: dict | None = None,
    output_part: dict | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    request_model: str | None = None,
    response_model: str | None = None,
):
    try:
        # common attributes
        app_name = tool_context._invocation_context.app_name
        user_id = tool_context._invocation_context.user_id
        agent_name = tool_context.agent_name
        session_id = tool_context._invocation_context.session.id
        span.set_attribute("gen_ai.agent.name", agent_name)
        span.set_attribute("openinference.instrumentation.veadk", VERSION)
        span.set_attribute("gen_ai.app.name", app_name)
        span.set_attribute("gen_ai.user.id", user_id)
        span.set_attribute("gen_ai.session.id", session_id)
        span.set_attribute("agent_name", agent_name)
        span.set_attribute("agent.name", agent_name)
        span.set_attribute("app_name", app_name)
        span.set_attribute("app.name", app_name)
        span.set_attribute("user.id", user_id)
        span.set_attribute("session.id", session_id)
        span.set_attribute("cozeloop.report.source", "veadk")

        # llm attributes
        span.set_attribute("gen_ai.system", "openai")
        span.set_attribute("gen_ai.operation.name", "chat")
        if request_model:
            span.set_attribute("gen_ai.request.model", request_model)
        if response_model:
            span.set_attribute("gen_ai.response.model", response_model)
        if total_tokens:
            span.set_attribute("gen_ai.usage.total_tokens", total_tokens)
        if output_tokens:
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        if input_tokens:
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        if input_part:
            span.add_event("gen_ai.user.message", input_part)
        if output_part:
            span.add_event("gen_ai.choice", output_part)

    except Exception:
        traceback.print_exc()
