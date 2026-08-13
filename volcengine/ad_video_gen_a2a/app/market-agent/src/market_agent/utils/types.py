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

from google.genai import types
from pydantic import BaseModel, Field

json_response_config = types.GenerateContentConfig(
    response_mime_type="application/json", max_output_tokens=18000
)


class Status(BaseModel):
    """A status."""

    success: bool = Field(description="True if the result is successful, otherwise False")
    message: str = Field(
        description="Empty when the run succeeds, otherwise the error message"
    )


# Description of the status field
"""
status field: the status field has two parts. When the business logic runs normally it is success: True, message: '';
otherwise it is success: False, message: '<error message>'.
Note: when the Agent encounters an execution problem, such as missing content, runtime errors, incomplete results,
or user input insufficient to complete the task, report it in the status field rather than describing it in the
business fields; in such cases the business fields may be left empty. Only report the error.
"status": {
            "success": bool, whether it succeeded
            "message": str, error message; empty string on success
        }
"""


class ProductInfo(BaseModel):
    """A product information."""

    name: str = Field(description="A Product's Name")
    selling_point: str = Field(description="The Product's Selling Point")
    resources: list[str] = Field(description="verified URL to an image of the product")
    audience: str = Field(description="The Product's Audience")


class VideoConfig(BaseModel):
    """Video configuration."""

    video_type: str = Field(description="The type of video to be generated")
    product_info: ProductInfo = Field(description="The product information")
    video_advice: str = Field(description="The video advice")
    status: Status = Field(description="The status of the video configuration")
