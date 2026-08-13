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

import re
import socket
import warnings
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from veadk.utils.logger import get_logger

# Suppress irrelevant warnings
warnings.filterwarnings("ignore")

# Logger configuration
logger = get_logger(__name__)

# Global browser instance (reused to avoid repeated startups and improve performance)
_global_browser = None


async def _init_browser():
    """Initialize the Playwright browser (reused globally)."""
    global _global_browser
    if not _global_browser:
        try:
            playwright = await async_playwright().start()
            # Launch the browser (selected automatically based on the system environment)
            _global_browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-images",
                    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ],
            )
            logger.info("Chromium browser initialized successfully")
        except Exception as e:
            logger.error(f"Browser initialization failed: {e}", exc_info=True)
            raise


def _is_public_ip(url: str) -> bool:
    """
    Check whether the URL resolves to a public IP address, to prevent SSRF attacks.
    """
    try:
        hostname = url.split("://")[1].split("/")[0].split(":")[0]
        ip_address = socket.gethostbyname(hostname)
        # Check whether the IP address is private, reserved, or loopback
        if ip_address.startswith(("10.", "172.", "192.168.", "127.", "169.254.")):
            return False
        return True
    except Exception:
        return False


async def parse_webpage_local(url: str, render_js: bool = True, delay: int = 5):
    """
    General-purpose web page parsing tool: extracts the list of image URLs and the plain text content of a web page (based on Playwright).
    :param url: Target web page URL
    :param render_js: Whether to render JS (for dynamic pages, default True)
    :param delay: Rendering delay (seconds, default 5)
    :return: (img_url_list, text_content)
    """
    global _global_browser

    logger.info(
        f"Starting web page parsing: {url}, render_js={render_js}, delay={delay}s"
    )

    # Initialize the browser (if not already initialized)
    if not _global_browser:
        await _init_browser()

    if not _global_browser:
        logger.error("Browser is not initialized")
        raise RuntimeError("Browser is not initialized")

    page = None
    try:
        # Create a new page
        context = await _global_browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        logger.debug("Created a new browser context and page")

        # Page request timeout configuration
        page.set_default_timeout(15 * 1000)  # 15-second timeout
        logger.debug("Set page timeout to 15 seconds")

        # Add DoS protection: check Content-Length
        try:
            with requests.get(url, stream=True, timeout=10) as r:
                content_length = r.headers.get("Content-Length")
                if content_length and int(content_length) > 10 * 1024 * 1024:  # 10MB
                    raise ValueError(
                        "Response content is larger than 10MB; parsing refused for safety"
                    )
        except requests.RequestException as e:
            logger.error(f"Error while checking response size: {e}")
            raise ValueError("Unable to access the URL")

        # Navigate to the target URL
        await page.goto(url, wait_until="domcontentloaded" if render_js else "commit")
        logger.info(f"Successfully accessed URL: {url}")

        # Render JS (wait for dynamic content to load)
        if render_js:
            logger.info(f"Waiting {delay} seconds for JS rendering")
            try:
                await page.wait_for_load_state("networkidle", timeout=delay * 1000)
            except Exception:
                import asyncio

                await asyncio.sleep(delay)  # Wait for the page to finish loading
            logger.debug("JS rendering finished")

        # Get the full page HTML
        html_content = await page.content()
        logger.debug(f"Fetched page HTML, length: {len(html_content)} characters")

        # 1. Extract all image URLs
        img_url_list = []

        # 1.1 Extract images from <img> tags (src/data-src/lazy-src, etc.)
        # Approach 1: extract via Playwright selectors (more efficient)
        img_elements = await page.query_selector_all("img")
        logger.debug(f"Found {len(img_elements)} img tags on the page")

        for img_elem in img_elements:
            # Get the image attributes
            img_src = (
                await img_elem.get_attribute("src")
                or await img_elem.get_attribute("data-src")
                or await img_elem.get_attribute("lazy-src")
                or await img_elem.get_attribute("data-lazy")
            )
            if img_src:
                absolute_url = urljoin(url, img_src)
                # Filter out invalid links
                if (
                    not absolute_url.startswith(
                        ("data:", "svg:", "javascript:", "blob:")
                    )
                    and "." in absolute_url.split("/")[-1]
                ):
                    img_url_list.append(absolute_url)
        logger.debug(f"Extracted {len(img_url_list)} valid images from img tags")

        # 1.2 Extract background images (background-image in style attributes)
        bg_pattern = re.compile(r'background-image:\s*url\(["\']?(.*?)["\']?\)', re.I)
        # Get the style attribute of every element
        all_elements = await page.query_selector_all("*")
        logger.debug(f"Checked {len(all_elements)} elements for background images")

        for elem in all_elements:
            style = await elem.get_attribute("style") or ""
            match = bg_pattern.search(style)
            if match:
                bg_img = match.group(1)
                absolute_bg_url = urljoin(url, bg_img)
                if (
                    absolute_bg_url not in img_url_list
                    and not absolute_bg_url.startswith(("data:", "svg:", "blob:"))
                ):
                    img_url_list.append(absolute_bg_url)
        logger.debug(
            f"Extracted {len(img_url_list) - len(set(img_url_list))} valid images from background styles"
        )

        # 1.3 Deduplicate
        img_url_list = list(set(img_url_list))
        logger.debug(f"Final image list after deduplication: {len(img_url_list)} images")

        # 2. Extract plain text content
        logger.debug("Extracting text content")
        soup = BeautifulSoup(html_content, "html.parser")
        # Remove useless tags
        for useless_tag in soup(
            ["script", "style", "noscript", "iframe", "header", "footer"]
        ):
            useless_tag.extract()
        # Format the text
        raw_text = soup.get_text(strip=True)
        text_content = re.sub(r"\s+", " ", raw_text)
        logger.debug(f"Extracted text content, length: {len(text_content)} characters")

        logger.info(
            f"Parsing finished: found {len(img_url_list)} images, text length {len(text_content)} characters"
        )
        return img_url_list, text_content

    except Exception as e:
        logger.error(f"Failed to parse web page: {e}", exc_info=True)
        raise
    finally:
        # Close the page and context to release resources
        if page:
            await page.close()
        if "context" in locals():
            await context.close()
