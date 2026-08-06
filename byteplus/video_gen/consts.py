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
import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_BUCKET = "video_generation_output"
DEFAULT_REGION = "ap-southeast-1"

DEFAULT_ARK_API_BASE = "https://ark.ap-southeast.bytepluses.com/api/v3"

DEFAULT_MODEL_AGENT_NAME = "deepseek-v4-pro-260425"
DEFAULT_MODEL_AGENT_API_BASE = DEFAULT_ARK_API_BASE

DEFAULT_VIDEO_MODEL_NAME = "dreamina-seedance-2-0-260128"
DEFAULT_VIDEO_MODEL_API_BASE = DEFAULT_ARK_API_BASE

DEFAULT_IMAGE_GENERATE_MODEL_NAME = "dola-seedream-5-0-pro-260628"
DEFAULT_IMAGE_GENERATE_MODEL_API_BASE = DEFAULT_ARK_API_BASE


def set_veadk_environment_variables():
    # veadk keys its BytePlus behavior off CLOUD_PROVIDER, not the
    # AGENTKIT_CLOUD_PROVIDER variable the agentkit SDK reads: with
    # CLOUD_PROVIDER=byteplus, veadk switches its own endpoint/model defaults
    # to BytePlus and maps BYTEPLUS_ACCESS_KEY/BYTEPLUS_SECRET_KEY onto the
    # VOLCENGINE_* variables it uses internally (veadk/config.py). veadk
    # snapshots all of this when first imported, so this function must run
    # before any veadk import.
    os.environ.setdefault(
        "CLOUD_PROVIDER", os.getenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    )

    os.environ["MODEL_AGENT_NAME"] = os.getenv(
        "MODEL_AGENT_NAME", DEFAULT_MODEL_AGENT_NAME
    )
    os.environ["MODEL_AGENT_API_BASE"] = os.getenv(
        "MODEL_AGENT_API_BASE", DEFAULT_MODEL_AGENT_API_BASE
    )

    os.environ["MODEL_VIDEO_NAME"] = os.getenv(
        "MODEL_VIDEO_NAME", DEFAULT_VIDEO_MODEL_NAME
    )
    os.environ["MODEL_VIDEO_API_BASE"] = os.getenv(
        "MODEL_VIDEO_API_BASE", DEFAULT_VIDEO_MODEL_API_BASE
    )

    os.environ["MODEL_IMAGE_NAME"] = os.getenv(
        "MODEL_IMAGE_NAME", DEFAULT_IMAGE_GENERATE_MODEL_NAME
    )
    os.environ["MODEL_IMAGE_API_BASE"] = os.getenv(
        "MODEL_IMAGE_API_BASE", DEFAULT_IMAGE_GENERATE_MODEL_API_BASE
    )
