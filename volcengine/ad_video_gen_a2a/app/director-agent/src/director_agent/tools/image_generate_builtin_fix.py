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
import base64
import concurrent.futures
import contextvars
import json
import mimetypes
import traceback
from typing import Dict

from google.adk.tools import ToolContext
from google.genai.types import Blob, Part
from opentelemetry import trace
from opentelemetry.trace import Span
from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime.types.images.images import SequentialImageGenerationOptions

from veadk.config import getenv, settings
from veadk.consts import (
    DEFAULT_IMAGE_GENERATE_MODEL_API_BASE,
    DEFAULT_IMAGE_GENERATE_MODEL_NAME,
)
from veadk.utils.logger import get_logger
from veadk.utils.misc import formatted_timestamp, read_file_to_bytes
from veadk.version import VERSION

logger = get_logger(__name__)

client = Ark(
    api_key=getenv(
        "MODEL_IMAGE_API_KEY", getenv("MODEL_AGENT_API_KEY", settings.model.api_key)
    ),
    base_url=getenv("MODEL_IMAGE_API_BASE", DEFAULT_IMAGE_GENERATE_MODEL_API_BASE),
)

executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
tracer = trace.get_tracer("veadk")


def _build_input_parts(item: dict, task_type: str, image_field):
    input_part = {"role": "user"}
    input_part["parts.0.type"] = "text"
    input_part["parts.0.text"] = json.dumps(item, ensure_ascii=False)

    if image_field:
        if task_type.startswith("single"):
            assert isinstance(image_field, str), (
                f"single_* task_type image must be str, got {type(image_field)}"
            )
            input_part["parts.1.type"] = "image_url"
            input_part["parts.1.image_url.name"] = "origin_image"
            input_part["parts.1.image_url.url"] = image_field
        elif task_type.startswith("multi"):
            assert isinstance(image_field, list), (
                f"multi_* task_type image must be list, got {type(image_field)}"
            )
            assert len(image_field) <= 10, (
                f"multi_* task_type image list length must be <= 10, got {len(image_field)}"
            )
            for i, image_url in enumerate(image_field):
                idx = i + 1
                input_part[f"parts.{idx}.type"] = "image_url"
                input_part[f"parts.{idx}.image_url.name"] = f"origin_image_{i}"
                input_part[f"parts.{idx}.image_url.url"] = image_url

    return input_part


def handle_single_task_sync(
    idx: int, item: dict, tool_context
) -> tuple[list[dict], list[str]]:
    logger.debug(f"handle_single_task_sync item {idx}: {item}")
    success_list: list[dict] = []
    error_list: list[str] = []
    total_tokens = 0
    output_tokens = 0
    output_part = {"message.role": "model"}

    task_type = item.get("task_type", "text_to_single")
    prompt = item.get("prompt", "")
    response_format = item.get("response_format", None)
    size = item.get("size", None)
    watermark = item.get("watermark", None)
    image_field = item.get("image", None)
    sequential_image_generation = item.get("sequential_image_generation", None)
    max_images = item.get("max_images", None)

    input_part = _build_input_parts(item, task_type, image_field)

    inputs = {"prompt": prompt}
    if size:
        inputs["size"] = size
    if response_format:
        inputs["response_format"] = response_format
    if watermark is not None:
        inputs["watermark"] = watermark
    if sequential_image_generation:
        inputs["sequential_image_generation"] = sequential_image_generation
    if image_field is not None:
        inputs["image"] = [image_field]

    with tracer.start_as_current_span(f"call_llm_task_{idx}") as span:
        try:
            if (
                sequential_image_generation
                and sequential_image_generation == "auto"
                and max_images
            ):
                response = client.images.generate(
                    model=getenv("MODEL_IMAGE_NAME", DEFAULT_IMAGE_GENERATE_MODEL_NAME),
                    **inputs,
                    sequential_image_generation_options=SequentialImageGenerationOptions(
                        max_images=max_images
                    ),
                    extra_headers={
                        "veadk-source": "veadk",
                        "veadk-version": VERSION,
                        "User-Agent": f"VeADK/{VERSION}",
                        "X-Client-Request-Id": getenv(
                            "MODEL_AGENT_CLIENT_REQ_ID", f"veadk/{VERSION}"
                        ),
                    },
                )
            else:
                response = client.images.generate(
                    model=getenv("MODEL_IMAGE_NAME", DEFAULT_IMAGE_GENERATE_MODEL_NAME),
                    **inputs,
                    extra_headers={
                        "veadk-source": "veadk",
                        "veadk-version": VERSION,
                        "User-Agent": f"VeADK/{VERSION}",
                        "X-Client-Request-Id": getenv(
                            "MODEL_AGENT_CLIENT_REQ_ID", f"veadk/{VERSION}"
                        ),
                    },
                )

            if not response.error:
                logger.debug(f"task {idx} Image generate response: {response}")

                total_tokens += getattr(response.usage, "total_tokens", 0) or 0
                output_tokens += getattr(response.usage, "output_tokens", 0) or 0

                for i, image_data in enumerate(response.data):
                    image_name = f"task_{idx}_image_{i}"
                    if "error" in image_data:
                        logger.error(f"Image {image_name} error: {image_data.error}")
                        error_list.append(image_name)
                        continue

                    if getattr(image_data, "url", None):
                        image_url = image_data.url
                    else:
                        b64 = getattr(image_data, "b64_json", None)
                        if not b64:
                            logger.error(
                                f"Image {image_name} missing data (no url/b64)"
                            )
                            error_list.append(image_name)
                            continue
                        image_bytes = base64.b64decode(b64)
                        image_url = _upload_image_to_tos(
                            image_bytes=image_bytes, object_key=f"{image_name}.png"
                        )
                        if not image_url:
                            logger.error(f"Upload image to TOS failed: {image_name}")
                            error_list.append(image_name)
                            continue
                        logger.debug(f"Image saved as ADK artifact: {image_name}")

                    tool_context.state[f"{image_name}_url"] = image_url
                    output_part[f"message.parts.{i}.type"] = "image_url"
                    output_part[f"message.parts.{i}.image_url.name"] = image_name
                    output_part[f"message.parts.{i}.image_url.url"] = image_url
                    logger.debug(
                        f"Image {image_name} generated successfully: {image_url}"
                    )
                    success_list.append({image_name: image_url})
            else:
                logger.error(
                    f"Task {idx} No images returned by model: {response.error}"
                )
                error_list.append(f"task_{idx}")

        except Exception as e:
            logger.error(f"Error in task {idx}: {e}")
            traceback.print_exc()
            error_list.append(f"task_{idx}")

        finally:
            add_span_attributes(
                span,
                tool_context,
                input_part=input_part,
                output_part=output_part,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                request_model=getenv(
                    "MODEL_IMAGE_NAME", DEFAULT_IMAGE_GENERATE_MODEL_NAME
                ),
                response_model=getenv(
                    "MODEL_IMAGE_NAME", DEFAULT_IMAGE_GENERATE_MODEL_NAME
                ),
            )
    logger.debug(
        f"task {idx} Image generate success_list: {success_list}\nerror_list: {error_list}"
    )
    return success_list, error_list


async def image_generate(tasks: list[dict], tool_context) -> Dict:
    """Generate images with Seedream 4.0.

    Commit batch image generation requests via tasks.

    Args:
        tasks (list[dict]):
            A list of image-generation tasks. Each task is a dict.
    Per-task schema
    ---------------
    Required:
        - task_type (str):
            One of:
              * "multi_image_to_group"   # multiple images -> image group
              * "single_image_to_group"  # single image -> image group
              * "text_to_group"          # text -> image group
              * "multi_image_to_single"  # multiple images -> single image
              * "single_image_to_single" # single image -> single image
              * "text_to_single"         # text -> single image
        - prompt (str)
            Text description of the desired image(s), in English or Chinese.
            To specify how many images to generate, add "generate N images" to
            the prompt, where N is a concrete number.
    Optional:
        - size (str)
            Specifies the size of the generated image(s). There are two usage
            modes (choose one; do not mix them):
            Mode 1: resolution level
                Allowed values: "1K", "2K", "4K"
                The model infers a suitable aspect ratio and dimensions from
                the semantics of the prompt.
            Mode 2: explicit width and height
                Format: "<width>x<height>", e.g. "2048x2048", "2384x1728"
                Constraints:
                    * Total pixel count range: [1024x1024, 4096x4096]
                    * Aspect ratio range: [1/16, 16]
                Recommended values:
                    - 1:1   → 2048x2048
                    - 4:3   → 2384x1728
                    - 3:4   → 1728x2304
                    - 16:9  → 2560x1440
                    - 9:16  → 1440x2560
                    - 3:2   → 2496x1664
                    - 2:3   → 1664x2496
                    - 21:9  → 3024x1296
            Default: "2048x2048"
        - response_format (str)
            Return format: "url" (default, URL expires after 24h) | "b64_json".
        - watermark (bool)
            Add watermark. Default: true.
        - image (str | list[str])   # Only for non-text-to-image tasks. Do not provide image for text-to-image tasks.
            Reference image(s) as URL or Base64.
            * Tasks generating a single image: pass a string (exactly 1 image).
            * Tasks generating an image group: pass an array (2-10 images).
        - sequential_image_generation (str)
            Controls whether an image group is generated. Default: "disabled".
            * To generate an image group: must be set to "auto".
        - max_images (int)
            Only takes effect when generating an image group. Controls the
            maximum number of images the model can generate, in the range
            [1, 15]; defaults to 15 if unset.
            Note that this parameter is not the number of images to generate,
            but the maximum number of images the model may generate.
            For single-image-to-group tasks the maximum is 14; for
            multi-image-to-group tasks it must satisfy (len(images)+max_images ≤ 15).
    Model behavior (how the mode is inferred from the parameters)
    ---------------------------------
    1) Text to single image: no image provided and (S unset or S="disabled") → 1 image.
    2) Text to image group: no image provided and S="auto" → image group, count controlled by max_images.
    3) Single image to single image: image=string and (S unset or S="disabled") → 1 image.
    4) Single image to image group: image=string and S="auto" → image group, count ≤14.
    5) Multiple images to single image: image=array (2-10) and (S unset or S="disabled") → 1 image.
    6) Multiple images to image group: image=array (2-10) and S="auto" → image group, total must be ≤15.
    Returns
    --------
        Dict with generation summary.
        Example:
        {
            "status": "success",
            "success_list": [
                {"image_name": "url"}
            ],
            "error_list": ["image_name"]
        }
    Notes:
    - Image group tasks must set sequential_image_generation="auto".
    - To specify how many images an image group should contain, state the count in the prompt, e.g. "generate 3 images".
    - For size, 2048x2048 or one of the standard ratios in the table above is recommended to ensure generation quality.
    """
    model = getenv("MODEL_IMAGE_NAME", DEFAULT_IMAGE_GENERATE_MODEL_NAME)

    if model.startswith("doubao-seedream-3-0"):
        logger.error(
            f"Image generation by Doubao Seedream 3.0 ({model}) is deprecated. Please use a newer Seedream model (e.g., doubao-seedream-5-0-pro-260628) instead."
        )
        return {
            "status": "failed",
            "success_list": [],
            "error_list": [
                "Image generation by Doubao Seedream 3.0 ({model}) is deprecated. Please use a newer Seedream model (e.g., doubao-seedream-5-0-pro-260628) instead."
            ],
        }

    logger.debug(f"Using model to generate image: {model}")

    success_list: list[dict] = []
    error_list: list[str] = []

    logger.debug(f"image_generate tasks: {tasks}")

    with tracer.start_as_current_span("image_generate"):
        base_ctx = contextvars.copy_context()

        def make_task(idx, item):
            ctx = base_ctx.copy()
            return lambda: ctx.run(handle_single_task_sync, idx, item, tool_context)

        loop = asyncio.get_event_loop()
        futures = [
            loop.run_in_executor(executor, make_task(idx, item))
            for idx, item in enumerate(tasks)
        ]

        results = await asyncio.gather(*futures, return_exceptions=True)

        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Task raised exception: {res}")
                error_list.append("unknown_task_exception")
                continue
            s, e = res
            success_list.extend(s)
            error_list.extend(e)

    if not success_list:
        logger.debug(
            f"image_generate success_list: {success_list}\nerror_list: {error_list}"
        )
        return {
            "status": "error",
            "success_list": success_list,
            "error_list": error_list,
        }
    app_name = tool_context._invocation_context.app_name
    user_id = tool_context._invocation_context.user_id
    session_id = tool_context._invocation_context.session.id
    artifact_service = tool_context._invocation_context.artifact_service

    if artifact_service:
        for image in success_list:
            for _, image_tos_url in image.items():
                filename = f"artifact_{formatted_timestamp()}"
                await artifact_service.save_artifact(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=session_id,
                    filename=filename,
                    artifact=Part(
                        inline_data=Blob(
                            display_name=filename,
                            data=read_file_to_bytes(image_tos_url),
                            mime_type=mimetypes.guess_type(image_tos_url)[0],
                        )
                    ),
                )

    logger.debug(
        f"image_generate success_list: {success_list}\nerror_list: {error_list}"
    )
    return {"status": "success", "success_list": success_list, "error_list": error_list}


def add_span_attributes(
    span: Span,
    tool_context: ToolContext,
    input_part: dict = None,
    output_part: dict = None,
    input_tokens: int = None,
    output_tokens: int = None,
    total_tokens: int = None,
    request_model: str = None,
    response_model: str = None,
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


def _upload_image_to_tos(image_bytes: bytes, object_key: str) -> None:
    try:
        import os
        from datetime import datetime

        from veadk.integrations.ve_tos.ve_tos import VeTOS

        timestamp: str = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
        object_key = f"{timestamp}-{object_key}"
        bucket_name = os.getenv("DATABASE_TOS_BUCKET")
        ve_tos = VeTOS()

        tos_url = ve_tos.build_tos_signed_url(
            object_key=object_key, bucket_name=bucket_name
        )

        ve_tos.upload_bytes(
            data=image_bytes, object_key=object_key, bucket_name=bucket_name
        )

        return tos_url
    except Exception as e:
        logger.error(f"Upload to TOS failed: {e}")
        return None
