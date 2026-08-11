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


def set_veadk_environment_variables():
    """Point veadk at BytePlus before it is first imported.

    veadk keys its BytePlus behavior off CLOUD_PROVIDER, not the
    AGENTKIT_CLOUD_PROVIDER variable the agentkit SDK reads: with
    CLOUD_PROVIDER=byteplus, veadk switches its own endpoint/model defaults to
    BytePlus and maps BYTEPLUS_ACCESS_KEY/BYTEPLUS_SECRET_KEY onto the
    VOLCENGINE_* variables it uses internally (veadk/config.py). veadk
    snapshots all of this when first imported, so this function must run
    before any veadk import.

    Unlike the other BytePlus samples, this one deliberately does *not* pin
    model names or API bases here: this sample is configured through
    `config.yaml` (see `config.yaml.example`), and veadk lets an environment
    variable that is already set win over the matching `config.yaml` key — so
    setting MODEL_* here would silently override the user's config file.
    """
    os.environ.setdefault(
        "CLOUD_PROVIDER", os.getenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    )
