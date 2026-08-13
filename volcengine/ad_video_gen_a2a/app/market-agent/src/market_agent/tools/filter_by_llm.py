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
import json
import os
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

# These tools consume images, so they need a vision-capable model (the main
# agent model, DeepSeek V4 Pro, is text-only).
DEFAULT_VISION_MODEL_NAME = "doubao-seed-2-1-turbo-260628"

filter_agent_instructions = """
You are a professional image filter serving a product-image-related task.
You will receive one image as input. It comes from a web page link and was extracted through web page parsing or a similar mechanism.
Based on the image content, decide whether the image shows a product, or is irrelevant content such as web page assets or decoration.
You do not need to return any reasoning; only decide yes or no. No extra output is allowed.
Note: if you cannot tell whether it is a product, then it is not.

### Reference output
{
    "is_good": true
}
"""

summarize_text_instructions = """
You are a professional text summarizer serving a product-image-related task.
You will receive a piece of text as input. It comes from a web page link and was extracted through web page parsing or a similar mechanism.
Summarize the main content of the text, including the product's name, price, description, and features.
"""


class IsGood(BaseModel):
    is_good: bool


def repair_image_input(image_list: list[str]) -> list[dict[str, Any]]:
    result = []
    for image in image_list:
        image_part = {
            "type": "input_image",
            "image_url": image,
        }  # References are always images
        result.append(image_part)

    return result


async def filter_images(image_list: list[str]) -> list[str]:
    inputs = repair_image_input(image_list)
    client = AsyncOpenAI(
        base_url=os.getenv("MODEL_AGENT_API_BASE"),
        api_key=os.getenv("MODEL_AGENT_API_KEY"),
    )
    sem = asyncio.Semaphore(10)  # Limit concurrency

    async def process_message(_input):
        async with sem:
            try:
                response = await client.responses.create(
                    model=os.getenv("MODEL_VISION_NAME", DEFAULT_VISION_MODEL_NAME),
                    instructions=filter_agent_instructions,
                    input=[{"role": "user", "content": [_input]}],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "IsGood",
                            "schema": IsGood.model_json_schema(),
                            "strict": True,
                        }
                    },
                    extra_body={"thinking": {"type": "disabled"}},
                )
                x = json.loads(response.output_text).get("is_good", False)
            except Exception:
                x = False
            return _input["image_url"] if x else None

    result = await asyncio.gather(*(process_message(_input) for _input in inputs))
    result = [r for r in result if r is not None]
    return result


async def summarize_text(text: str):
    client = AsyncOpenAI(
        base_url=os.getenv("MODEL_AGENT_API_BASE"),
        api_key=os.getenv("MODEL_AGENT_API_KEY"),
    )
    try:
        response = await client.responses.create(
            model=os.getenv("MODEL_VISION_NAME", DEFAULT_VISION_MODEL_NAME),
            instructions=summarize_text_instructions,
            input=text[0:10000],
            extra_body={"thinking": {"type": "disabled"}},
        )
        return response.output_text
    except Exception:
        return text[0:10000]
