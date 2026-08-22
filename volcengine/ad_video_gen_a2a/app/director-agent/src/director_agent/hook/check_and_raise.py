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

from typing import Any, Optional

from google.adk.tools import BaseTool, ToolContext

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def error_status(tool_name: str, reason: str) -> dict:
    """Create a standardized error dictionary for tool responses."""
    return {"status": {"success": False, "message": f"{tool_name} Error: {reason}"}}


# Without the underlying API error the model only learns that the item count is
# short, so its only move is to resubmit the very same parameters - which fails
# the same way, forever. Hand it the per-item reason plus an explicit
# instruction to change something or give up.
RETRY_HINT = (
    " Do NOT resubmit the same parameters unchanged: fix the cause reported "
    "above first. If the cause is not something you can fix by editing the "
    "request, stop retrying and report the failure in the status field."
)

# Some failures are a verdict on what the request *contains* - a moderation
# rejection of the prompt or of the first-frame image - rather than on how it
# was written. Nothing the model can edit turns those into a success, so telling
# it to "fix the cause" only sends it round the same loop. Name them and say
# plainly that the content has to change or the item has to go.
PERMANENT_HINT = (
    " {names} {verb} rejected for what the request contains - its prompt or its "
    "first-frame image - not for how it was written, so resubmitting cannot "
    "succeed however the parameters are edited. Either change the "
    "content itself (a different first frame, a reworded prompt) or leave those "
    "items out and report the failure in the status field."
)


def retry_hint(tool_response: dict) -> str:
    """Tell the model whether resubmitting could possibly help."""
    permanent = [str(name) for name in (tool_response.get("permanent_failures") or [])]
    if not permanent:
        return RETRY_HINT

    hint = PERMANENT_HINT.format(
        names=", ".join(permanent), verb="was" if len(permanent) == 1 else "were"
    )
    # Anything that failed for some other reason may still be worth one retry.
    if len(permanent) < len(tool_response.get("error_list") or []):
        hint += RETRY_HINT
    return hint


def failure_detail(tool_response: dict) -> str:
    """Render the per-item failure reasons the tool reported, if any."""
    errors = tool_response.get("errors") or {}
    if isinstance(errors, dict) and errors:
        # De-duplicate: a whole batch usually fails for one and the same reason.
        by_reason: dict[str, list[str]] = {}
        for name, reason in errors.items():
            by_reason.setdefault(str(reason), []).append(str(name))
        lines = [f"{', '.join(names)}: {reason}" for reason, names in by_reason.items()]
        return " Reported failures - " + "; ".join(lines) + "."

    failed = tool_response.get("error_list") or []
    if failed:
        return f" Failed items: {failed}."
    return ""


def raise_result_error(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext, tool_response: Any
) -> Optional[Any]:
    """
    Post-execution hook to validate the results of image and video generation tools.

    This hook checks if the number of generated media items matches the number
    requested in the tool's input arguments.

    - For `image_generate`, it calculates the expected number of images based on
      the `tasks` list, considering both single and group generation requests.
    - For `video_generate`, it checks the number of videos requested in the `params` list.

    If a mismatch is found, it returns a formatted error dictionary to halt
    the workflow and notify the user.
    """
    if tool.name == "image_generate":
        try:
            tasks = args.get("tasks", [])
            if not tasks:
                return None  # No tasks to check

            # Calculate the total number of images expected from all tasks
            total_expected_images = 0
            for task in tasks:
                task_type = task.get("task_type", "")
                is_group_task = "group" in task_type
                if is_group_task:
                    total_expected_images += task.get("max_images", 1)
                else:
                    total_expected_images += 1

            logger.debug(f"Expected {total_expected_images} images to be generated.")

            if isinstance(tool_response, dict):
                success_list = tool_response.get("success_list", [])
                actual_images = len(success_list)

                if actual_images != total_expected_images:
                    reason = (
                        f"The total number of generated images ({actual_images}) does not match the expected count ({total_expected_images})."
                        + failure_detail(tool_response)
                        + retry_hint(tool_response)
                    )
                    logger.warning(reason)
                    return error_status(tool.name, reason)
            else:
                logger.warning(
                    f"Tool response for {tool.name} is not a dict: {tool_response}"
                )

        except Exception as e:
            logger.error(f"Error while validating results for {tool.name}: {e}")
        return None

    elif tool.name == "video_generate":
        try:
            params = args.get("params", [])
            if not params:
                return None  # No params to check

            total_expected_videos = len(params)
            logger.debug(f"Expected {total_expected_videos} videos to be generated.")

            if isinstance(tool_response, dict):
                success_list = tool_response.get("success_list", [])
                actual_videos = len(success_list)

                if actual_videos != total_expected_videos:
                    reason = (
                        f"The total number of generated videos ({actual_videos}) does not match the expected count ({total_expected_videos})."
                        + failure_detail(tool_response)
                        + retry_hint(tool_response)
                    )
                    logger.warning(reason)
                    return error_status(tool.name, reason)
            else:
                logger.warning(
                    f"Tool response for {tool.name} is not a dict: {tool_response}"
                )

        except Exception as e:
            logger.error(f"Error while validating results for {tool.name}: {e}")
        return None

    return None
