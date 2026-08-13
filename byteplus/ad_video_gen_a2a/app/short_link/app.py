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
import hashlib
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Mode configuration
SHORT_LINK_MODE = os.getenv(
    "SHORT_LINK_MODE", "dict"
)  # Defaults to dict mode; allowed values: "redis", "dict"

# Conditionally import Redis
if SHORT_LINK_MODE == "redis":
    try:
        import redis.asyncio as redis

        REDIS_AVAILABLE = True
    except ImportError:
        logging.getLogger("short_link").warning(
            "Redis mode selected but the redis library is not installed; run: pip install redis. Falling back to dict mode."
        )
        REDIS_AVAILABLE = False
        SHORT_LINK_MODE = "dict"  # Fall back to dict mode
else:
    REDIS_AVAILABLE = False

# Lightweight logging
logger = logging.getLogger("short_link")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# Create the FastAPI app
app = FastAPI(
    title="Short Link Service",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Storage backend initialization
if SHORT_LINK_MODE == "redis" and REDIS_AVAILABLE:
    # Connect to Redis
    storage_client = redis.Redis(
        host=os.getenv("REDIS_HOST"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        username=os.getenv("REDIS_USERNAME"),
        password=os.getenv("REDIS_PASSWORD"),
        db=int(os.getenv("REDIS_DB", 0)),
        decode_responses=True,
    )
else:
    # Use a dict as the storage backend
    logger.info(f"Storing short links in dict mode (SHORT_LINK_MODE={SHORT_LINK_MODE})")
    # Initialize the dict storage
    dict_storage = {
        "auto_id_counter": 0,
        "long_md5": {},  # long:md5:{md5} -> short_code
        "short": {},  # short:{short_code} -> url
    }

    # Mimic the Redis client's async interface
    class DictStorageClient:
        def __init__(self, storage):
            self.storage = storage

        async def get(self, key: str):
            if key.startswith("long:md5:"):
                md5 = key.replace("long:md5:", "")
                return self.storage["long_md5"].get(md5)
            elif key.startswith("short:"):
                short_code = key.replace("short:", "")
                return self.storage["short"].get(short_code)
            return None

        async def setex(self, key: str, ttl: int, value: str):
            # Dict mode does not support TTL, but keep the interface compatible
            if key.startswith("long:md5:"):
                md5 = key.replace("long:md5:", "")
                self.storage["long_md5"][md5] = value
            elif key.startswith("short:"):
                short_code = key.replace("short:", "")
                self.storage["short"][short_code] = value

        async def incr(self, key: str):
            if key == "auto_id:counter":
                self.storage["auto_id_counter"] += 1
                return self.storage["auto_id_counter"]
            return 0

    storage_client = DictStorageClient(dict_storage)

# Character set for base conversion
CHAR_SET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE = len(CHAR_SET)


def encode_id(unique_id: int) -> str:
    """
    Convert an auto-increment ID into a short code
    :param unique_id: Auto-increment ID
    :return: Short code
    """
    if unique_id == 0:
        return CHAR_SET[0]
    short_code = []
    while unique_id > 0:
        unique_id, remainder = divmod(unique_id, BASE)
        short_code.append(CHAR_SET[remainder])
    return "".join(reversed(short_code))


class URLRequest(BaseModel):
    url: str
    type: str = None


@app.post("/shorten", response_model=dict)
async def shorten_url(request: URLRequest):
    """
    Generate a short link
    :param url: Original long URL
    :return: Short code and short link
    """
    # Compute the MD5 hash of the URL
    url = request.url
    url_md5 = hashlib.md5(url.encode()).hexdigest()

    # Check whether a short code has already been generated for this long URL
    existing_short_code = await storage_client.get(f"long:md5:{url_md5}")
    if existing_short_code:
        domain = os.getenv("SHORT_LINK_DOMAIN", "http://localhost:8005")
        if request.type:
            short_url = f"{domain}/t/{request.type}/{existing_short_code}"
        else:
            short_url = f"{domain}/t/{existing_short_code}"
        return {
            "short_code": existing_short_code,
            "short_url": short_url,
        }

    # Get an auto-increment ID
    unique_id = await storage_client.incr("auto_id:counter")

    # Convert the auto-increment ID into a short code
    short_code = encode_id(unique_id)

    # Store the core mappings
    await storage_client.setex(f"long:md5:{url_md5}", 24 * 3600, short_code)
    await storage_client.setex(f"short:{short_code}", 24 * 3600, url)

    # Return the result
    domain = os.getenv("SHORT_LINK_DOMAIN", "http://localhost:8005")
    if request.type:
        short_url = f"{domain}/t/{request.type}/{short_code}"
    else:
        short_url = f"{domain}/t/{short_code}"
    return {"short_code": short_code, "short_url": short_url}


@app.get("/t/{short_code}")
@app.get("/t/{type}/{short_code}")
async def redirect_url(short_code: str, type: str = None):
    """
    Short link redirect
    :param type: Resource type (optional)
    :param short_code: Short code
    :return: Redirect to the original long URL
    """
    # Get the original long URL
    url = await storage_client.get(f"short:{short_code}")
    if not url:
        raise HTTPException(status_code=404, detail="Short code not found")
    return url.strip('"')
