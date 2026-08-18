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
"""Optional `.env` loading for an ad_video_gen_a2a service.

Import and call `load_env_file()` before any veadk / agentkit import: veadk
snapshots the environment (including `config.yaml`) when first imported.
"""

import logging
import os
from pathlib import Path

from dotenv import dotenv_values

logger = logging.getLogger(__name__)

# Directories searched for a `.env` file, highest priority first. The current
# working directory is always searched last.
_ENV_FILE_DIRS = [
    Path(__file__).resolve().parent,  # this service's src/ dir
    Path(__file__).resolve().parents[1],  # service dir (next to config.yaml)
    Path(__file__).resolve().parents[3],  # ad_video_gen_a2a project root
]


def load_env_file() -> list[Path]:
    """Load environment variables from `.env` files (optional).

    Precedence: values in a `.env` file win over variables already exported in
    the shell; anything not present in any `.env` file falls back to the shell
    environment. Files are searched in `_ENV_FILE_DIRS` and then the current
    working directory; when several exist, the earlier (project-side) file wins
    for keys they share. Missing files are ignored.

    Returns the list of `.env` files that were loaded.
    """
    loaded: list[Path] = []
    seen: set[Path] = set()
    for directory in [*_ENV_FILE_DIRS, Path.cwd()]:
        env_file = (directory / ".env").resolve()
        if env_file in seen or not env_file.is_file():
            continue
        seen.add(env_file)
        loaded.append(env_file)

    merged: dict[str, str] = {}
    # Apply lowest-priority (CWD) first so higher-priority files override it.
    for env_file in reversed(loaded):
        merged.update(
            {k: v for k, v in dotenv_values(env_file).items() if v is not None}
        )
    os.environ.update(merged)

    for env_file in loaded:
        logger.info(f"[consts] Loaded environment variables from {env_file}")
    return loaded

