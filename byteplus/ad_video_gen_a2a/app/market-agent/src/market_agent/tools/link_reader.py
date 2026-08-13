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

from typing import Any
from urllib.parse import urlparse

from market_agent.tools.image_understand import comment_image
from market_agent.tools.is_image import batch_check_images
from market_agent.tools.web_parse import parse_webpage
from market_agent.tools.filter_by_llm import summarize_text, filter_images
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


async def read_url_link(link_list: list[str]) -> str | list[dict[str, Any]]:
    """
    Read and parse web page content.

    This asynchronous method invokes the `LinkReader` tool to parse the web page
    content/images of the given URLs and returns the parsing results.

    Args:
        link_list (list[str]): List of web page links to parse.

    Returns:
        Case 1:
        list[dict[str, Any]]: List of parsed web page/image contents.
        Each dictionary contains the following key-value pairs:
        Parsing results are returned for each link in order
        - 'images': list[str] List of image URLs.
        - 'text': str Text description of the image/web page.
    """
    logger.debug(f"Starting to parse links: {link_list}")
    is_images_results = await batch_check_images(link_list)
    logger.debug(f"Image detection results: {is_images_results}")
    result = []
    for i, link in enumerate(link_list):
        # try:
        # Each element in is_images_results is a tuple of (url, is_image, reason)
        _, is_image, _ = is_images_results[i]
        if is_image:
            res = await comment_image(link)
            result.append(res)
            continue
        else:
            # Invoke the `LinkReader` tool to fetch and parse web page content (avoid printing the full link to the console)
            logger.debug(
                f"Calling parse_webpage to parse link domain: {urlparse(link).netloc}"
            )
            images, text = await parse_webpage(link)
            # Filter out invalid image links
            images = await filter_images(images)
            # Summarize the text content
            text = await summarize_text(text)
            logger.debug(
                f"For url: {link} \n Parsed image count: {len(images)}, parsed text length {len(text)}"
            )
            if len(text) < 100:
                logger.debug(f"For url: {link} \n Text too short, length: {len(text)}")
            if len(images) > 5:
                logger.debug(
                    f"For url: {link} \n Too many images, keeping the first 5"
                )
                images = images[:5]
            result.append({"images": images, "text": text})

        # except Exception as e:
        #     # Catch and log the exception
        #     logger.error(f"Error parsing {link}: {e}")
        #     # Continue with the next link
        #     result.append({"images": [], "text": ""})

    return result
