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
import aiohttp
import requests
from typing import List, Tuple

# Image magic-number mapping (signature of the first N bytes)
IMAGE_MAGIC_NUMBERS = {
    b"\xff\xd8\xff": "jpeg",  # JPG/JPEG
    b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a": "png",  # PNG
    b"\x47\x49\x46\x38\x37\x61": "gif",  # GIF87a
    b"\x47\x49\x46\x38\x39\x61": "gif",  # GIF89a
    b"\x52\x49\x46\x46": "webp",  # WebP (starts with RIFF, WEBP verified later)
    b"\x42\x4d": "bmp",  # BMP
    b"\x3c\x73\x76\x67": "svg",  # SVG (text starting with <svg)
}


def is_image_resource(
    url: str, timeout: float = 3.0, allow_redirects: bool = True
) -> Tuple[bool, str]:
    """
    Synchronously check whether a single URL is an image resource (validates HTTP headers/file content only, not the URL suffix)
    :param url: URL to check
    :param timeout: Timeout in seconds
    :param allow_redirects: Whether to allow redirects
    :return: (is_image, verification basis)
             Verification basis is one of: content_type / magic_number / error
    """
    # Step 1: issue a lightweight request (HEAD first, fall back to GET on failure)
    try:
        # 1. Try a HEAD request (fetches only the response headers, fastest)
        resp = requests.head(
            url,
            timeout=timeout,
            allow_redirects=allow_redirects,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        # 2. If HEAD fails, fall back to GET (reads only the headers, does not download the body)
        if resp.status_code != 200:
            resp = requests.get(
                url,
                timeout=timeout,
                allow_redirects=allow_redirects,
                stream=True,  # Key point: do not download the body
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            )

        # 3. Validate Content-Type (highest priority, lowest cost)
        content_type = resp.headers.get("Content-Type", "").lower()
        if content_type.startswith("image/"):
            return True, "content_type"

        # Step 2: if Content-Type is unreliable, validate the file magic number (downloads only the first 16 bytes)
        try:
            # Read the first 16 bytes (enough to cover all image magic numbers)
            header_bytes = resp.raw.read(16) if resp.raw else b""
            # Match magic numbers
            for magic, _ in IMAGE_MAGIC_NUMBERS.items():
                if header_bytes.startswith(magic):
                    # Extra WebP check (RIFF must be followed by WEBP)
                    if magic == b"\x52\x49\x46\x46" and b"WEBP" not in header_bytes:
                        continue
                    # Extra SVG check (text format, must be case-insensitive)
                    if (
                        magic == b"\x3c\x73\x76\x67"
                        and not header_bytes.lower().startswith(b"<svg")
                    ):
                        continue
                    return True, "magic_number"
            return False, "content_type"
        finally:
            resp.close()  # Force-close the connection to avoid resource leaks

    except Exception as e:
        # Catch all exceptions (timeouts, network errors, SSL errors, etc.)
        return False, f"error: {str(e)[:50]}"


async def async_is_image_resource(
    url: str, session: aiohttp.ClientSession, timeout: float = 3.0
) -> Tuple[str, bool, str]:
    """
    Asynchronously check whether a single URL is an image resource (preferred for batch scenarios)
    :param url: URL to check
    :param session: aiohttp session (reuses connections to improve batch performance)
    :param timeout: Timeout in seconds
    :return: (url, is_image, verification basis)
    """
    timeout_obj = aiohttp.ClientTimeout(total=timeout)
    try:
        # 1. Issue a GET request (aiohttp has poor HEAD support, use GET + stream directly)
        async with session.get(
            url,
            timeout=timeout_obj,
            allow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        ) as resp:
            # 2. Validate Content-Type
            content_type = resp.headers.get("Content-Type", "").lower()
            if content_type.startswith("image/"):
                return url, True, "content_type"

            # 3. Validate the magic number (reads only the first 16 bytes)
            header_bytes = await resp.content.read(16)
            for magic, _ in IMAGE_MAGIC_NUMBERS.items():
                if header_bytes.startswith(magic):
                    if magic == b"\x52\x49\x46\x46" and b"WEBP" not in header_bytes:
                        continue
                    if (
                        magic == b"\x3c\x73\x76\x67"
                        and not header_bytes.lower().startswith(b"<svg")
                    ):
                        continue
                    return url, True, "magic_number"
            return url, False, "content_type"

    except Exception as e:
        return url, False, f"error: {str(e)[:50]}"


async def batch_check_images(
    urls: List[str],
    timeout: float = 3.0,
    max_concurrency: int = 50,  # Concurrency level
) -> List[Tuple[str, bool, str]]:
    """
    Batch-check URLs asynchronously to determine whether they are image resources
    :param urls: List of URLs
    :param timeout: Timeout per URL
    :param max_concurrency: Maximum concurrency
    :return: A list where each element is (url, is_image, verification basis)
    """
    # Limit concurrency (to avoid being blocked for sending too many requests)
    semaphore = asyncio.Semaphore(max_concurrency)

    async def bounded_check(url):
        async with semaphore:
            return await async_is_image_resource(url, session, timeout)

    # Create a reusable aiohttp session (improves performance)
    connector = aiohttp.TCPConnector(limit=0)  # Unlimited connection pool (controlled by the semaphore)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [bounded_check(url) for url in urls]
        results = await asyncio.gather(*tasks)
    return results
