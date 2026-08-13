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

import requests
import json
import traceback
import logging
import time
import os

test_dict = {
    "local": "http://localhost:8004/{}",  # 0: do not use
}

# Global variable holding the URL template
url_template = test_dict["local"]


def save_result(result, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)


def create_session(app_name, user_id):
    url = url_template.format(f"apps/{app_name}/users/{user_id}/sessions")

    payload = {}
    headers = {}

    response = requests.request("POST", url, headers=headers, data=payload)

    session_id = json.loads(response.text)["id"]
    logger.info(f"main output: session_id: {session_id}")
    return session_id


def pick_best_image(evaluate_image_result):
    best_image_list = []
    scored_image_list = evaluate_image_result["scored_image_list"]
    for shot in scored_image_list:
        # Pick the highest-scoring image from the images list, converting the score from string to float
        best_image = max(shot["images"], key=lambda x: max(float(x.get("score")), 0))

        # Build the new shot structure
        best_shot = {
            "shot_id": shot["shot_id"],
            "prompt": shot["prompt"],
            "action": shot["action"],
            "reference": shot["reference"],
            "words": shot["words"],
            "image": {"id": best_image["id"], "url": best_image["url"]},
        }

        best_image_list.append(best_shot)
    return best_image_list


def pick_best_video(evaluate_video_result):
    best_video_list = []
    scored_video_list = evaluate_video_result["scored_video_list"]

    for shot in scored_video_list:
        # Pick the highest-scoring video from the videos list, converting the score from string to float
        best_video = max(shot["videos"], key=lambda x: max(float(x.get("score")), 0))

        # Build the new shot structure
        best_shot = {
            "shot_id": shot["shot_id"],
            "prompt": shot["prompt"],
            "action": shot["action"],
            "reference": shot["reference"],
            "words": shot["words"],
            "video": {"id": best_video["id"], "url": best_video["url"]},
        }

        best_video_list.append(best_shot)
    return best_video_list


def run_sse(app_name, user_id, session_id, text):
    url = url_template.format("run_sse")
    # logger.info(f"main output: run_sse url: {url}")
    payload = json.dumps(
        {
            "app_name": app_name,
            "user_id": user_id,
            "session_id": session_id,
            "new_message": {"role": "user", "parts": [{"text": text}]},
        }
    )
    headers = {"Content-Type": "application/json"}

    try:
        # (1) Skip stream=True and wait for the complete response
        response = requests.post(url, headers=headers, data=payload, timeout=6000)
        response.raise_for_status()  # Raises on 4xx / 5xx responses
        logger.info(f"Raw response: {response.text[:500]}...")  # Print only the first 500 characters to keep logs short

        # (2) Parse the last data: block line by line (the server still returns SSE format)
        data_lines = [
            line for line in response.text.splitlines() if line.startswith("data: ")
        ]
        if not data_lines:
            logger.warning("No data: block found")
            return None

        last_data = data_lines[-1][6:]  # Strip the 'data: ' prefix
        event = json.loads(last_data)
        logger.info(
            f"Last event: {json.dumps(event, ensure_ascii=False, indent=2)}"
        )

        # (3) Extract the final content (assuming a fixed structure)
        return event["content"]["parts"][0]["text"]

    except requests.exceptions.Timeout:
        logger.error("Request timed out (over 6000 seconds)")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
    except (KeyError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse the response: {e}")

    return None


def main(user_need):
    # step 0: create session
    try:
        logger.info("main output: 0. Creating session...")
        session_id = create_session("demo_app", "user")
        save_result(session_id, tmp_json_dir + "0_session_id.json")
    except Exception as e:
        logger.info(f"main output: 0. create session failed: {e}")
        traceback.print_exc()
        return

    # step 1: generate video config
    try:
        logger.info("main output: 1. Generating the video configuration...")
        generate_video_config_input = user_need + "\nGenerate the video configuration"
        video_config = run_sse(
            "demo_app", "user", session_id, generate_video_config_input
        )
        logger.info(f"main output: 1. video_config: {video_config}")
        save_result(json.loads(video_config), tmp_json_dir + "1_video_config.json")
    except Exception as e:
        logger.info(f"main output: 1. run sse failed: {e}")
        traceback.print_exc()
        return

    # step 1.1: parse video_type
    try:
        logger.info("main output: 1.1 Parsing video_type...")
        logger.info(f"main output: 1.1 video_config: {video_config}")
        video_type = json.loads(video_config)["video_type"]
    except Exception as e:
        logger.info(f"main output: 1.1 get video_type failed: {e}")
        traceback.print_exc()
        return

    # step 2: generate shot list
    try:
        logger.info("main output: 2. Generating the storyboard script...")
        generate_shot_list_input = (
            "Generate the storyboard script from the following video_config\n\n" + video_config
        )
        shot_list = run_sse("demo_app", "user", session_id, generate_shot_list_input)
        logger.info(f"main output: 2. shot_list: {shot_list}")
        save_result(json.loads(shot_list), tmp_json_dir + "2_shot_list.json")
    except Exception as e:
        logger.info(f"main output: 2. run sse failed: {e}")
        traceback.print_exc()
        return

    # step 3: generate image list
    try:
        logger.info("main output: 3. Generating the storyboard images...")
        generate_image_list_input = "Generate the storyboard images from the following shot_list\n\n" + shot_list
        image_list = run_sse("demo_app", "user", session_id, generate_image_list_input)
        logger.info(f"main output: 3. image_list: {image_list}")
        save_result(json.loads(image_list), tmp_json_dir + "3_image_list.json")
    except Exception as e:
        logger.info(f"main output: 3. run sse failed: {e}")
        traceback.print_exc()
        return

    # step 4: evaluate image list
    try:
        logger.info("main output: 4. Evaluating the storyboard images...")
        evaluate_image_list_input = (
            "Evaluate the quality of the storyboard images from the following storyboard image list image_list\n\n" + image_list
        )
        evaluate_image_result = run_sse(
            "demo_app", "user", session_id, evaluate_image_list_input
        )
        logger.info(f"main output: 4. evaluate_image_result: {evaluate_image_result}")
        save_result(
            json.loads(evaluate_image_result),
            tmp_json_dir + "4_evaluate_image_list.json",
        )
    except Exception as e:
        logger.info(f"main output: 4. run sse failed: {e}")
        traceback.print_exc()
        return

    # step 4.1: pick best image
    try:
        logger.info("main output: 4.1 Picking the best storyboard images...")
        best_image_list = pick_best_image(json.loads(evaluate_image_result))
        save_result(best_image_list, tmp_json_dir + "4_1_selected_image_list.json")
        logger.info(f"main output: 4.1 best_image_list: {best_image_list}")
    except Exception as e:
        logger.info(f"main output: 4.1 pick best image failed: {e}")
        traceback.print_exc()
        return

    # step 5: generate video list
    try:
        logger.info("main output: 5. Generating the storyboard videos...")
        generate_video_list_input = (
            "Generate the storyboard videos from the following image_list, generating 4 videos per shot\n\n"
            + str(best_image_list)
        )
        video_list = run_sse("demo_app", "user", session_id, generate_video_list_input)
        logger.info(f"main output: 5. video_list: {video_list}")
        save_result(json.loads(video_list), tmp_json_dir + "5_video_list.json")
    except Exception as e:
        logger.info(f"main output: 5. run sse failed: {e}")
        traceback.print_exc()
        return

    # step 6: evaluate video list
    try:
        logger.info("main output: 6. Evaluating the storyboard videos...")
        evaluate_video_list_input = (
            "Evaluate the quality of the storyboard videos from the following storyboard video list video_list\n\n" + str(video_list)
        )
        logger.info(
            f"main output: 6. evaluate_video_list_input: {evaluate_video_list_input}"
        )
        evaluate_video_result = run_sse(
            "demo_app", "user", session_id, evaluate_video_list_input
        )
        logger.info(f"main output: 6. evaluate_video_result: {evaluate_video_result}")
        save_result(
            json.loads(evaluate_video_result),
            tmp_json_dir + "6_evaluate_video_list.json",
        )
    except Exception as e:
        logger.info(f"main output: 6. run sse failed: {e}")
        traceback.print_exc()
        return

    # step 6.1: pick best video
    try:
        logger.info("main output: 6.1 Picking the best storyboard videos...")
        best_video_list = pick_best_video(json.loads(evaluate_video_result))
        save_result(best_video_list, tmp_json_dir + "6_1_selected_video_list.json")
        logger.info(f"main output: 6.1 best_video_list: {best_video_list}")
    except Exception as e:
        logger.info(f"main output: 6.1 pick best video failed: {e}")
        traceback.print_exc()
        return

    # step 7: generate final video
    try:
        logger.info("main output: 7. Generating the final video...")
        generate_final_video_input = f"Compose the final video of type: {video_type}\n\n" + str(
            best_video_list
        )

        logger.info(f"main output: 7. session_id: {session_id}")
        logger.info(
            f"main output: 7. generate_final_video_input: {generate_final_video_input}"
        )

        final_video = run_sse(
            "demo_app", "user", session_id, generate_final_video_input
        )
        logger.info(f"main output: 7. final_video: {final_video}")
        save_result(final_video, tmp_json_dir + "7_final_video.json")
    except Exception as e:
        logger.info(f"main output: 7. run sse failed: {e}")
        traceback.print_exc()
        return


if __name__ == "__main__":
    # Default run mode: local
    t_type = "local"

    # Create the temporary output directory
    time_start = t_type + "-" + str(time.time())
    tmp_json_dir = "tmp-json/" + str(time_start) + "/"
    os.makedirs(tmp_json_dir, exist_ok=True)

    # Configure logging
    log_name = time.time()
    log_file_path = tmp_json_dir + "full/"
    os.makedirs(log_file_path, exist_ok=True)
    log_file_name = log_file_path + str(log_name) + ".log"

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file_name, encoding="utf-8"),  # Write to file
            logging.StreamHandler(),  # Print to console
        ],
    )
    logger = logging.getLogger(__name__)

    user_need = "Generate a promotional video (Product Showcase Video) for a waxberry drink. Product image: https://ark-tutorial.tos-cn-beijing.volces.com/multimedia/%E6%9D%A8%E6%A2%85%E9%A5%AE%E6%96%99.jpg"
    logger.info(f"!!!! main output: test_type:{t_type}, url_template: {url_template}")

    # Run the pipeline
    main(user_need)
