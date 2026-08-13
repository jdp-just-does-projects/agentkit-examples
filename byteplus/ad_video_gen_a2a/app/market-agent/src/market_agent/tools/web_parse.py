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

from veadk.utils.logger import get_logger
from .web_parser_local import parse_webpage_local

logger = get_logger(__name__)


async def parse_webpage(url, render_js=True, delay=5):
    """
    General-purpose web page parsing tool: extracts the list of image URLs and the plain text content of a web page
    :param url: Target web page URL
    :param render_js: Whether to render JS (for dynamic pages, default True)
    :param delay: Rendering delay (seconds, default 5)
    :return: (img_url_list, text_content)
             img_url_list: List of image URLs (deduplicated, absolute paths)
             text_content: Plain text content of the web page (whitespace and line breaks removed)
    """
    logger.debug(f"Starting local web page parsing: {url}")

    try:
        # Invoke the local web page parsing function
        img_url_list, text_content = await parse_webpage_local(url, render_js, delay)

        logger.debug(
            f"Parsing finished: found {len(img_url_list)} images, text preview length {len(text_content)} characters"
        )
        return img_url_list, text_content

    except Exception as e:
        logger.error(f"Local web page parsing failed: {e}")
        return [], f"Web page parsing failed: {str(e)}"
