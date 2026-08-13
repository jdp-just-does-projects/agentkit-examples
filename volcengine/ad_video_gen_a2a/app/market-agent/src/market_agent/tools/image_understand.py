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
from typing import Any

from openai import AsyncOpenAI
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

# This tool consumes images, so it needs a vision-capable model (the main
# agent model, DeepSeek V4 Pro, is text-only).
DEFAULT_VISION_MODEL_NAME = "doubao-seed-2-1-turbo-260628"

filter_agent_instructions = """
You are a professional image understanding and review expert, currently supporting an e-commerce marketing video planning workflow.
Your job is to look at the image you receive, understand its content, and give a detailed description.
For example, if you receive an e-commerce image of a pair of shoes, describe what kind of shoes they are: color, style, and type — canvas shoes or sneakers.
Also describe supporting details of the product, such as its features, target audience, and usage scenarios.

Your output supports the completion of the overall e-commerce marketing plan.
"""


def repair_image_input(image: str) -> dict[str, Any]:
    image_part = {
        "type": "input_image",
        "image_url": image,
    }  # References are always images
    return image_part


async def comment_image(image: str) -> dict[str, Any]:
    logger.debug(f"Calling image_understand to analyze image: {image}")
    image_part = repair_image_input(image)
    client = AsyncOpenAI(
        base_url=os.getenv("MODEL_AGENT_API_BASE"),
        api_key=os.getenv("MODEL_AGENT_API_KEY"),
    )
    response = await client.responses.create(
        model=os.getenv("MODEL_VISION_NAME", DEFAULT_VISION_MODEL_NAME),
        instructions=filter_agent_instructions,
        input=[{"role": "user", "content": [image_part]}],
        extra_body={"thinking": {"type": "disabled"}},
    )
    return {"image": image, "text": response.output_text}
