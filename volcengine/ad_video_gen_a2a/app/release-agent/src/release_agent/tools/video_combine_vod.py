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
from typing import List, Dict, Any
from typing import Optional
import urllib.parse
import aiohttp
import fastmcp
from fastmcp import Client
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

# Short link service configuration
shorten_url_service_url = os.getenv("SHORTEN_URL_SERVICE_URL", None)
assert shorten_url_service_url, (
    "SHORTEN_URL_SERVICE_URL is not set. Set it in config.yaml "
    "(shorten_url_service_url) or export it before starting the service."
)


async def resolve_short_url(short_url: str) -> str:
    """
    Resolve a short link back to its original URL

    Args:
        short_url: The short link URL

    Returns:
        The original URL; if resolution fails, the short link itself is returned
    """
    # Avoid printing the short link to the console; use structured logging instead
    logger.debug("Resolving short URL")
    if not shorten_url_service_url:
        return short_url

    try:
        # Extract the short code from the short link
        # Short link format: http://127.0.0.1:8005/t/AbC123 or http://127.0.0.1:8005/t/video/AbC123
        parsed_url = urllib.parse.urlparse(short_url)
        path_parts = parsed_url.path.strip("/").split("/")

        if len(path_parts) >= 2 and path_parts[0] == "t":
            # Call the short link service's redirect endpoint to get the original URL
            async with aiohttp.ClientSession() as session:
                # Use a GET request to fetch the original URL (the short link service returns the original URL string directly)
                async with session.get(short_url) as response:
                    if response.status == 200:
                        # The short link service returns the original URL string directly
                        original_url = await response.text()
                        original_url = original_url.strip().strip('"')
                        logger.debug(
                            f"Successfully resolved short URL: {short_url} -> {original_url}"
                        )
                        return original_url
                    else:
                        logger.warning(
                            f"Failed to resolve short URL: {short_url}, status: {response.status}"
                        )
                        return short_url
        else:
            logger.warning(f"Not a valid short URL format: {short_url}")
            return short_url

    except Exception as e:
        logger.error(f"Error resolving short URL {short_url}: {e}")
        # If resolution fails, return the original short link
        return short_url


vod_mcp_config = {
    "mcpServers": {
        "mcp-server-vod": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/volcengine/mcp-server.git#subdirectory=server/mcp_server_vod",
                "mcp-server-vod",
            ],
            "env": {
                "VOLCENGINE_ACCESS_KEY": os.getenv("VOLCENGINE_ACCESS_KEY"),
                "VOLCENGINE_SECRET_KEY": os.getenv("VOLCENGINE_SECRET_KEY"),
            },
        }
    }
}


class VodToolSet:
    def __init__(
        self,
        mcp_config: dict,
        space_name: Optional[str] = None,
        task_polling_interval: int = 20,
        max_retries: int = 30,
    ):
        self.mcp_client = Client(mcp_config)
        self.space_name = space_name
        self.task_polling_interval = task_polling_interval
        self.max_retries = max_retries

    async def list_tools(self):
        async with self.mcp_client as client:
            response = await client.list_tools()
            return response

    async def _call_tools(self, tool_name: str, arguments: dict[str, Any]):
        async with self.mcp_client as client:
            response = await client.call_tool(
                name=tool_name,
                arguments=arguments,
            )

            return [
                json.loads(content.model_dump().get("text", ""))
                for content in response.content
            ]

    async def video_stitching(self, videos_url: list[str]) -> dict:
        new_videos_url = []
        for item in videos_url:
            item = resolve_short_url(item)
            new_videos_url.append(item)

        response = await self._call_tools(
            tool_name="audio_video_stitching",
            arguments={
                "type": "video",
                "SpaceName": self.space_name,
                "videos": new_videos_url,
            },
        )

        task_id = response[0]["VCreativeId"]

        for _ in range(self.max_retries):
            response = await self._get_task_message(task_id)
            status = response.get("Status", "error")
            if status in {"success", "failed_run"}:
                break
            elif status == "error":
                return {
                    "film_url": "",
                    "success": False,
                    "message": "The video composition tool is busy; please retry.",
                }
            else:
                await asyncio.sleep(self.task_polling_interval)
        else:
            return {"url": "", "status": "timeout"}

        return {
            "film_url": response.get("OutputJson", {}).get("url", ""),
            "success": status == "success",
            "message": status,
        }

    async def _get_task_message(self, task_id: str) -> dict:
        try:
            response = await self._call_tools(
                tool_name="get_v_creative_task_result",
                arguments={"VCreativeId": task_id, "SpaceName": self.space_name},
            )
            status = response[0]
            return status
        except fastmcp.exceptions.ToolError as e:
            logger.error(
                f"Error getting task message: fastmcp.exceptions.ToolError: {e}"
            )
            return {"Status": "mcp_error"}

    async def generate(self, video_list: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Process the video list:
        {
            "video": {"url": "xxx"},
            "audio": {"url": "xxx"}  # optional
        }
        """

        if not video_list:
            raise ValueError("video_list not found")

        videos: list = []

        for i, shot in enumerate(video_list, start=1):
            video_info = shot.get("video", {})
            video_url = video_info.get("url") if isinstance(video_info, dict) else None
            if not video_url:
                raise ValueError(f"shot[{i}] missing video.url")

            videos.append(video_url)

        video_product = videos
        # Step 2: stitch these videos together
        result = await self.video_stitching(video_product)

        logger.debug(f"[video_combine] result: {result}")
        return result


async def video_combine(video_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Tool Name:
        video_combine

    Description:
        This tool edits and stitches multiple video clips (shots) into one complete video in the given order.    Each video clip carries its own visual description (prompt), action description (action), and video file information.
        The tool can be used to automatically produce ad videos, product showcase clips, or creative short films.

    Args:
        video_list (List[Dict]):
            A list of video clips (shots), where each element is a dict with the following fields:
            - shot_id (str):
                Unique identifier of the current shot.
            - prompt (str):
                Detailed visual description of the shot, covering composition, subject, lighting, atmosphere, etc.
            - action (str):
                Text description of the camera movement, transition, or effects, e.g. "the camera slowly pushes in" or "accompanied by a lens-flare effect".
            - video (Dict):
                Video file information for the current shot, containing:
                    - id (str): Unique identifier of the video file in the system.
                    - url (str): Accessible URL of the video file (e.g. an object storage link).
            - audio (Dict, optional):
                Audio file information for the current shot, containing:
                    - id (str): Unique identifier of the audio file in the system.
                    - url (str): Accessible URL of the audio file.

    Returns:
        output_video (str):
            Path or accessible URL of the stitched video file.

    Example:
        >>> video_list = [
        ...     {
        ...         "shot_id": "shot_1",
        ...         "prompt": "The subject is a transparent glass bottle of Wangmeihao bayberry juice, with the red bayberry juice clearly visible inside...",
        ...         "action": "The camera slowly rotates and pushes in on the bottle from a wide shot",
        ...         "video": {"id": "1", "url": "https://example.com/video1.mp4"},
        ...         "audio": {"id": "1", "url": "https://example.com/audio1.mp3"}
        ...     },
        ...     ...
        ... ]
        >>> result = video_combine(video_list)
        >>> print(result)
        {
            "film_url": 'https://example.com/merged_video.mp4',
            "status": "success"
        }

    Notes:
        - All input videos should have compatible resolutions and frame rates; otherwise, preprocess them to unify these parameters.
        - The tool stitches the videos in the order given by video_list.
    """
    vod_tool_set = VodToolSet(
        space_name=os.getenv("TOOLS_VOD_SPACE_NAME", None),
        task_polling_interval=int(os.getenv("TOOLS_VOD_TASK_POLLING_INTERVAL", "20")),
        max_retries=int(os.getenv("TOOLS_VOD_MAX_RETRIES", "60")),
        mcp_config=vod_mcp_config,
    )
    try:
        film_url = await vod_tool_set.generate(video_list)

        return film_url
    except Exception as e:
        logger.error(f"Failed to generate film: {e}")
        return {
            "film_url": "",
            "success": False,
            "message": "The video composition tool failed; please retry.",
        }
