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
import logging
import sys
import time
import os

test_dict = {
    "local": "http://localhost:8004/{}",  # 0: do not use
}

# Global variable holding the URL template
url_template = test_dict["local"]


# How much of an agent's answer to quote in an error message. Long enough to
# see what went wrong, short enough not to bury the log in a 500-character URL.
SNIPPET = 400


class AgentError(RuntimeError):
    """The agent service answered, but the answer is a failure, not a result.

    Raised for transport failures, HTTP errors, and - the case worth naming -
    an SSE event whose task state is ``failed``. That last one used to reach
    the caller as an ordinary string containing a provider error message,
    which then died at ``json.loads`` as ``Expecting value: line 1 column 1
    (char 0)``, four lines away from the thing that actually broke.
    """


class AgentOutputError(RuntimeError):
    """The agent succeeded, but its answer is not the JSON this step expects."""


def save_result(result, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)


def event_failure(event):
    """``(state, error_code, message)`` if this SSE event reports a failure.

    Two places record one. ADK sets ``errorCode``/``errorMessage`` on the event
    when the agent itself raised; when the answer came from a remote agent over
    A2A, the relayed task carries the outcome in ``customMetadata``:

        customMetadata["a2a:response"]["status"]["state"]        # "failed"
        customMetadata["a2a:response"]["metadata"]["adk_error_code"]
    """
    error_code = event.get("errorCode")
    message = event.get("errorMessage")

    response = (event.get("customMetadata") or {}).get("a2a:response") or {}
    state = (response.get("status") or {}).get("state")
    error_code = error_code or (response.get("metadata") or {}).get("adk_error_code")

    if error_code or state in ("failed", "rejected", "canceled"):
        return state or "failed", error_code, message
    return None


def event_text(event):
    """The text the agent finished with, or ``None`` if it wrote none."""
    for part in (event.get("content") or {}).get("parts") or []:
        if part.get("text"):
            return part["text"]
    return None


def parse_and_save(text, step, filename):
    """Parse a step's answer as JSON and save it, or explain why it is not JSON.

    On failure the raw answer is written next to the run's other artefacts, so
    the payload survives even when the console output is gone.
    """
    if not text or not text.strip():
        raise AgentOutputError(f"{step}: the agent returned an empty answer")
    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raw_path = tmp_json_dir + filename + ".raw.txt"
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(text)
        raise AgentOutputError(
            f"{step}: the agent's answer is not JSON ({e}). "
            f"It starts {text[:SNIPPET]!r} and the whole answer is in {raw_path}"
        ) from e
    save_result(result, tmp_json_dir + filename)
    return result


def fail(step, exc):
    """Log a step failure and tell ``main`` to stop.

    ``AgentError`` and ``AgentOutputError`` carry their own explanation; a
    traceback would only bury it. Anything else is a bug here, so log the
    traceback - through the logger, so it reaches the run's log file too.
    """
    detail = str(exc)
    # run_sse and parse_and_save already name the step in their message; don't
    # say it twice.
    if detail.startswith(step + ":"):
        detail = detail[len(step) + 1 :].lstrip()

    if isinstance(exc, (AgentError, AgentOutputError)):
        logger.error(f"main output: {step} failed: {detail}")
    else:
        logger.exception(f"main output: {step} failed: {detail}")
    return False


def create_session(app_name, user_id):
    url = url_template.format(f"apps/{app_name}/users/{user_id}/sessions")

    payload = {}
    headers = {}

    try:
        response = requests.request("POST", url, headers=headers, data=payload)
    except requests.exceptions.RequestException as e:
        raise AgentError(
            f"could not reach the agent service at {url} - is it running? ({e})"
        ) from e
    if not response.ok:
        raise AgentError(
            f"the agent service answered HTTP {response.status_code} for {url}: "
            f"{response.text[:SNIPPET]}"
        )

    try:
        session_id = json.loads(response.text)["id"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise AgentError(
            f"the agent service did not return a session id ({e}): "
            f"{response.text[:SNIPPET]}"
        ) from e
    logger.info(f"main output: session_id: {session_id}")
    return session_id


def pick_best_image(evaluate_image_result):
    if "scored_image_list" not in evaluate_image_result:
        raise AgentOutputError(
            "the evaluate agent returned no `scored_image_list`; it returned "
            f"{sorted(evaluate_image_result)}"
        )
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
    if "scored_video_list" not in evaluate_video_result:
        raise AgentOutputError(
            "the evaluate agent returned no `scored_video_list`; it returned "
            f"{sorted(evaluate_video_result)}"
        )
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


def run_sse(app_name, user_id, session_id, text, step="run_sse"):
    """Send one request to the agent service and return the final answer text.

    Raises ``AgentError`` instead of returning ``None`` when anything goes
    wrong, so a failure is reported where it happens and with the reason
    attached, rather than surfacing as an unrelated parse error one step later.
    """
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

    # (1) Skip stream=True and wait for the complete response
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=6000)
    except requests.exceptions.Timeout as e:
        raise AgentError(f"{step}: the agent did not answer within 6000 seconds") from e
    except requests.exceptions.RequestException as e:
        raise AgentError(f"{step}: the request to {url} failed: {e}") from e

    if not response.ok:
        # requests' own HTTPError message omits the body, which is where the
        # service explains itself.
        raise AgentError(
            f"{step}: the agent service answered HTTP {response.status_code}: "
            f"{response.text[:SNIPPET]}"
        )
    logger.info(f"Raw response: {response.text[:500]}...")  # Print only the first 500 characters to keep logs short

    # (2) Parse the last data: block line by line (the server still returns SSE format)
    data_lines = [
        line for line in response.text.splitlines() if line.startswith("data: ")
    ]
    if not data_lines:
        raise AgentError(
            f"{step}: the response carried no `data:` block: {response.text[:SNIPPET]}"
        )

    last_data = data_lines[-1][6:]  # Strip the 'data: ' prefix
    try:
        event = json.loads(last_data)
    except json.JSONDecodeError as e:
        raise AgentError(
            f"{step}: the last SSE event is not JSON ({e}): {last_data[:SNIPPET]}"
        ) from e
    logger.info(
        f"Last event: {json.dumps(event, ensure_ascii=False, indent=2)}"
    )

    # (3) A failed run also ends with a well-formed event - the failure is in
    # its metadata, and the text part holds the provider's error message.
    # Report it here rather than handing that message on as if it were output.
    failure = event_failure(event)
    if failure:
        state, error_code, message = failure
        detail = message or event_text(event) or json.dumps(event, ensure_ascii=False)
        raise AgentError(
            f"{step}: the {event.get('author', app_name)} agent finished in state "
            f"'{state}'{f' ({error_code})' if error_code else ''}: {detail[:SNIPPET]}"
        )

    # (4) Extract the final content
    final_text = event_text(event)
    if final_text is None:
        raise AgentError(
            f"{step}: the agent's last event carries no text: "
            f"{json.dumps(event.get('content'), ensure_ascii=False)[:SNIPPET]}"
        )
    return final_text


def main(user_need):
    """Run the pipeline end to end. Returns True on success, False on failure."""
    # step 0: create session
    try:
        logger.info("main output: 0. Creating session...")
        session_id = create_session("demo_app", "user")
        save_result(session_id, tmp_json_dir + "0_session_id.json")
    except Exception as e:
        return fail("0. create session", e)

    # step 1: generate video config
    try:
        logger.info("main output: 1. Generating the video configuration...")
        generate_video_config_input = user_need + "\nGenerate the video configuration"
        video_config = run_sse(
            "demo_app", "user", session_id, generate_video_config_input,
            step="1. generate the video configuration",
        )
        logger.info(f"main output: 1. video_config: {video_config}")
        video_config_data = parse_and_save(
            video_config, "1. generate the video configuration", "1_video_config.json"
        )
    except Exception as e:
        return fail("1. generate the video configuration", e)

    # step 1.1: parse video_type
    try:
        logger.info("main output: 1.1 Parsing video_type...")
        logger.info(f"main output: 1.1 video_config: {video_config}")
        video_type = video_config_data["video_type"]
    except Exception as e:
        found = (
            sorted(video_config_data)
            if isinstance(video_config_data, dict)
            else type(video_config_data).__name__
        )
        return fail(
            f"1.1 read video_type from the video configuration (it holds {found})", e
        )

    # step 2: generate shot list
    try:
        logger.info("main output: 2. Generating the storyboard script...")
        generate_shot_list_input = (
            "Generate the storyboard script from the following video_config\n\n" + video_config
        )
        shot_list = run_sse(
            "demo_app", "user", session_id, generate_shot_list_input,
            step="2. generate the storyboard script",
        )
        logger.info(f"main output: 2. shot_list: {shot_list}")
        parse_and_save(shot_list, "2. generate the storyboard script", "2_shot_list.json")
    except Exception as e:
        return fail("2. generate the storyboard script", e)

    # step 3: generate image list
    try:
        logger.info("main output: 3. Generating the storyboard images...")
        generate_image_list_input = "Generate the storyboard images from the following shot_list\n\n" + shot_list
        image_list = run_sse(
            "demo_app", "user", session_id, generate_image_list_input,
            step="3. generate the storyboard images",
        )
        logger.info(f"main output: 3. image_list: {image_list}")
        parse_and_save(image_list, "3. generate the storyboard images", "3_image_list.json")
    except Exception as e:
        return fail("3. generate the storyboard images", e)

    # step 4: evaluate image list
    try:
        logger.info("main output: 4. Evaluating the storyboard images...")
        evaluate_image_list_input = (
            "Evaluate the quality of the storyboard images from the following storyboard image list image_list\n\n" + image_list
        )
        evaluate_image_result = run_sse(
            "demo_app", "user", session_id, evaluate_image_list_input,
            step="4. evaluate the storyboard images",
        )
        logger.info(f"main output: 4. evaluate_image_result: {evaluate_image_result}")
        evaluate_image_data = parse_and_save(
            evaluate_image_result,
            "4. evaluate the storyboard images",
            "4_evaluate_image_list.json",
        )
    except Exception as e:
        return fail("4. evaluate the storyboard images", e)

    # step 4.1: pick best image
    try:
        logger.info("main output: 4.1 Picking the best storyboard images...")
        best_image_list = pick_best_image(evaluate_image_data)
        save_result(best_image_list, tmp_json_dir + "4_1_selected_image_list.json")
        logger.info(f"main output: 4.1 best_image_list: {best_image_list}")
    except Exception as e:
        return fail("4.1 pick the best storyboard images", e)

    # step 5: generate video list
    try:
        logger.info("main output: 5. Generating the storyboard videos...")
        generate_video_list_input = (
            "Generate the storyboard videos from the following image_list, generating 4 videos per shot\n\n"
            + str(best_image_list)
        )
        video_list = run_sse(
            "demo_app", "user", session_id, generate_video_list_input,
            step="5. generate the storyboard videos",
        )
        logger.info(f"main output: 5. video_list: {video_list}")
        parse_and_save(video_list, "5. generate the storyboard videos", "5_video_list.json")
    except Exception as e:
        return fail("5. generate the storyboard videos", e)

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
            "demo_app", "user", session_id, evaluate_video_list_input,
            step="6. evaluate the storyboard videos",
        )
        logger.info(f"main output: 6. evaluate_video_result: {evaluate_video_result}")
        evaluate_video_data = parse_and_save(
            evaluate_video_result,
            "6. evaluate the storyboard videos",
            "6_evaluate_video_list.json",
        )
    except Exception as e:
        return fail("6. evaluate the storyboard videos", e)

    # step 6.1: pick best video
    try:
        logger.info("main output: 6.1 Picking the best storyboard videos...")
        best_video_list = pick_best_video(evaluate_video_data)
        save_result(best_video_list, tmp_json_dir + "6_1_selected_video_list.json")
        logger.info(f"main output: 6.1 best_video_list: {best_video_list}")
    except Exception as e:
        return fail("6.1 pick the best storyboard videos", e)

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
            "demo_app", "user", session_id, generate_final_video_input,
            step="7. generate the final video",
        )
        logger.info(f"main output: 7. final_video: {final_video}")
        save_result(final_video, tmp_json_dir + "7_final_video.json")
    except Exception as e:
        return fail("7. generate the final video", e)

    logger.info("main output: done. The final video is in " + tmp_json_dir + "7_final_video.json")
    return True


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

    user_need = "Generate a promotional video (Product Showcase Video) for a Christmas limited dark chocolate gift box, warm festive style. Product image: http://lf3-static.bytednsdoc.com/obj/eden-cn/lm_sth/ljhwZthlaukjlkulzlp/ark/assistant/images/ad_chocolate.png"
    logger.info(f"!!!! main output: test_type:{t_type}, url_template: {url_template}")

    # Run the pipeline. A non-zero exit status means a step failed - the reason
    # is the last `failed:` line in the log.
    sys.exit(0 if main(user_need) else 1)
