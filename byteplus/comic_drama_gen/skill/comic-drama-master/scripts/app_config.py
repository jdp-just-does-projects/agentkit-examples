"""
Comic drama application configuration tool.
Reads the VIDEO_DURATION_MINUTES environment variable and outputs a JSON config.
Smart duration mode: each storyboard scene is dynamically allocated 4s ~ 15s
based on scene complexity.

Usage:
    python scripts/app_config.py
"""

import json
import os

SUPPORTED_DURATIONS = (0.5, 1, 2, 3, 4)

# Dynamic duration range: each storyboard scene can be allocated 4s ~ 15s
MIN_SCENE_DURATION = 4
MAX_SCENE_DURATION = 15


def get_app_config() -> dict:
    raw = os.environ.get("VIDEO_DURATION_MINUTES", "0.5").strip()
    try:
        minutes = float(raw)
    except ValueError:
        minutes = 0.5

    if minutes not in SUPPORTED_DURATIONS:
        minutes = 0.5

    # Smart duration mode: total duration = minutes * 60 seconds
    # Each storyboard scene can be dynamically allocated 4s ~ 15s for a richer, more varied pacing
    total_seconds = int(minutes * 60)
    # Scene count reference range: all-longest duration gives the lower bound, all-shortest gives the upper bound
    min_scenes = total_seconds // MAX_SCENE_DURATION  # Scene count if all scenes are 15s
    max_scenes = total_seconds // MIN_SCENE_DURATION  # Scene count if all scenes are 4s
    # Recommended scene count: estimated with an 8s average, balancing pacing variety
    avg_duration = (MIN_SCENE_DURATION + MAX_SCENE_DURATION) / 2
    recommended_scenes = round(total_seconds / avg_duration)

    return {
        "video_duration_minutes": minutes,
        "total_seconds": total_seconds,
        "smart_duration": True,
        "duration_range": {"min": MIN_SCENE_DURATION, "max": MAX_SCENE_DURATION},
        "duration_options": "4s ~ 15s dynamically allocated (4/5/6/7/8/9/10/11/12/13/14/15)",
        "scene_count_range": {"min": min_scenes, "max": max_scenes},
        "recommended_scene_count": recommended_scenes,
        "note": "Each storyboard scene's duration is decided dynamically by story pacing: tense quick cuts 4-6s, standard narration 7-10s, climax build-up 11-15s",
        "config_source": f"VIDEO_DURATION_MINUTES={raw}",
    }


if __name__ == "__main__":
    config = get_app_config()
    print(json.dumps(config, ensure_ascii=False, indent=2))
