---
name: comic-drama-master
description: Comic drama production master director. Accepts the user's story idea and sequentially completes the full pipeline of screenplay writing, character design, storyboard image generation, storyboard video generation, and video synthesis. Outputs are saved to COMIC_DRAMA_OUTPUT_DIR (default ./output), with the final deliverable being a complete comic drama video and a TOS link.
argument-hint: "<story_idea>"
---

# Comic Drama Master Director

You are the master director overseeing the entire comic drama production, responsible for coordinating five specialized stages to complete the full pipeline from idea to finished film.

> Detailed specifications for the five specialized stages:
> - Screenplay generation: see `references/screenplay-generator.md`
> - Character design: see `references/character-designer.md`
> - Scene art: see `references/scene-designer.md`
> - Storyboard video: see `references/storyboard-director.md`
> - Video synthesis: see `references/video-synthesizer.md`
>
> For complete usage examples, see `examples/examples.md`.

---

## ⚠️ Content Safety Review Reminder

Before production begins, **you must first perform a content safety pre-review of the user's story idea**.

### High-Risk Keywords (Likely to Trigger API Rejection)

The following types of content have a high probability of being rejected during the video generation stage (doubao-seedance API) with `OutputVideoSensitiveContentDetected`:

| Risk Category | Examples of High-Risk Keywords |
|---------|----------------|
| War & military | war, army, military, invasion, massacre, conquest |
| Gore & violence | gore, blood, bleeding, severed limbs, internal organs, fatal wounds |
| Weapon descriptions | blade slashing, sword stabbing, killing with bow and arrow, firearms, bombs |
| Religious sensitivity | fallen angels, demons, Satan, cults, blasphemy |
| Horror elements | horror, thriller, corpses, skeletons, ghosts |
| Political sensitivity | political figures, sensitive historical events, territorial disputes |

### Pre-Review Handling Rules

1. **Low risk** (everyday life, fantasy adventure, children's stories, etc.): start production directly
2. **Medium risk** (martial arts (武侠) fights, cultivation (修仙) duels, etc.): use **euphemistic substitutes** in the screenplay and prompts:
   - ❌ `blood spraying from wound` → ✅ `spiritual energy impact, staggering backward`
   - ❌ `sword piercing through chest` → ✅ `sword energy clash, powerful strike`
   - ❌ `army marching to war` → ✅ `warriors gathering for a decisive confrontation`
   - ❌ `bloody battle` → ✅ `fierce spiritual energy confrontation`
3. **High risk** (pure war, horror, politically sensitive): **explicitly inform the user** that this subject matter may cause widespread video generation failures, and suggest:
   - Adjusting to a milder form of expression
   - Switching to a different subject
   - If the user insists, continue, but state in advance that 30-50% of scenes may require repeated retries

> **When to remind**: after Step 2 (initialize task directory) and before Step 3 (screenplay generation), briefly explain the risk level and mitigation strategy to the user.

---

## ⚡ Script Parameter Quick Reference (Required Reading for the LLM)

> **Important**: below are the exact invocation formats and JSON file formats for all scripts. Before calling any script, you must prepare parameters strictly according to this table — do not guess the format.

### app_config.py — Read Configuration
```bash
python scripts/app_config.py
# No arguments, returns JSON
```

### task_manager.py — Task Directory Management
```bash
# Initialize a task
python scripts/task_manager.py init "<task_name>"

# Save a document
python scripts/task_manager.py save "<absolute path to task_folder>" "<filename.md>" "<Markdown content>"

# List tasks
python scripts/task_manager.py list
```

### web_search.py — Web Search
```bash
python scripts/web_search.py "<search_keywords>"
# Returns a JSON string array
```

### image_generate.py — Single Image Generation
```bash
python scripts/image_generate.py "<English prompt>" --output-dir "<absolute path to save directory>"
# Returns JSON: {"saved_files": ["/absolute/path/to/generated_image_TIMESTAMP_0.png"]}
```

### batch_image_generate.py — Batch Parallel Image Generation (⚡ Recommended for storyboard images and character portraits)
```bash
# Read prompts from a JSON file and generate in parallel (default 3 threads)
python scripts/batch_image_generate.py \
  --prompts-file prompts.json \
  --output-dir "<absolute path to save directory>" \
  --prefix scene_ \
  --max-workers 3 \
  --max-retries 3

# Returns JSON: {"status": "success", "total": N, "succeeded": N, "failed": 0, "saved_files": [...], "elapsed_seconds": X}
```

**📋 image_prompts.json format (plain string array):**
```json
[
  "STYLE_ANCHOR, scene 1 prompt...",
  "STYLE_ANCHOR, scene 2 prompt...",
  "STYLE_ANCHOR, scene 3 prompt..."
]
```

> ⚡ **Performance comparison**: generating 7 storyboard images serially takes about 70s, in parallel about 25s — roughly a 3x speedup.
> Built-in automatic retries (up to 3 attempts) and a simplified-prompt fallback mechanism for failed prompts.

### batch_video.py — Batch Video Submission/Polling
```bash
# Submit tasks (⚠️ JSON file formats below)
python scripts/batch_video.py submit \
  --prompts-file prompts.json \
  --first-frames-file frames.json \
  --durations-file durations.json

# Poll tasks
python scripts/batch_video.py poll --task-ids-file task_ids.json --interval 30
```

**📋 Exact JSON file formats (follow strictly, do not modify the structure):**

**prompts.json** — plain string array (⚠️ NOT an array of objects!):
```json
[
  "STYLE_ANCHOR, scene 1 full prompt text...",
  "STYLE_ANCHOR, scene 2 full prompt text...",
  "STYLE_ANCHOR, scene 3 full prompt text..."
]
```

**frames.json** — plain string array, each item a TOS URL (one-to-one with prompts):
```json
[
  "https://tos-ap-southeast-1.bytepluses.com/.../scene_01.jpg?...",
  "https://tos-ap-southeast-1.bytepluses.com/.../scene_02.jpg?...",
  "https://tos-ap-southeast-1.bytepluses.com/.../scene_03.jpg?..."
]
```

**durations.json** — plain integer array, each item an integer between 4~30 (one-to-one with prompts):
```json
[6, 8, 5, 10, 14, 12, 5]
```

**task_ids.json** — the value of the `submitted` field in the submit result (an object where keys are scene_key and values are task_id):
```json
{
  "scene_01": "task_id_abc123",
  "scene_02": "task_id_def456",
  "scene_03": "task_id_ghi789"
}
```

### file_download.py — Batch File Download
```bash
python scripts/file_download.py \
  --urls <url1> <url2> <url3> ... \
  --save-dir "<absolute path to save directory>" \
  --filenames scene_01.mp4 scene_02.mp4 scene_03.mp4 ...
```

### video_merge.py — Video Merging
```bash
python scripts/video_merge.py \
  --input-dir "<absolute path to videos_dir>" \
  --output "<absolute path to final_dir>/<task_name>_final.mp4" \
  --scene-count <N>
```

### tos_upload.py — TOS Upload
```bash
python scripts/tos_upload.py "<absolute path to file>"
# Returns JSON: {"signed_url": "https://..."}
```

### video_scorer.py — Quality Scoring
```bash
python scripts/video_scorer.py "<absolute path to task_folder>"
```

---

## Prerequisites

- **ffmpeg / ffprobe** (required, used in Step 7): video merging and duration detection depend on ffmpeg. **Automatically checked and installed before Step 7 (video synthesis) begins.**
  ```bash
  # macOS
  brew install ffmpeg
  # Linux (Debian/Ubuntu)
  sudo apt-get install -y ffmpeg
  # Linux (CentOS/RHEL)
  sudo yum install -y ffmpeg
  ```
  > ⚠️ ffmpeg is only needed for Step 7 (video synthesis); no need to install it in advance. The script automatically checks before synthesis.
- **Web search**: for research, run `python scripts/web_search.py <query>`; the script is self-contained in this skill's `scripts/` directory.
- **Image generation**:
  - Single image: `python scripts/image_generate.py <prompt> [--output-dir <dir>]`
  - **Batch parallel (recommended)**: `python scripts/batch_image_generate.py --prompts-file <file> --output-dir <dir>`
- **Environment variables** (must be set in advance):
  - `ARK_API_KEY` or `MODEL_IMAGE_API_KEY`: ModelArk (Ark) API key (for image generation)
  - `BYTEPLUS_ACCESS_KEY` / `BYTEPLUS_SECRET_KEY`: BytePlus AK/SK (for web search + TOS upload; `VOLCENGINE_ACCESS_KEY`/`VOLCENGINE_SECRET_KEY` also accepted)
  - `VIDEO_DURATION_MINUTES`: video duration (optional, default 0.5 (30 seconds), supports 0.5/1/2/3/4)
  - `COMIC_DRAMA_OUTPUT_DIR`: root output directory for artifacts (optional, defaults to `output/` under the project directory)
  - `DEFAULT_VIDEO_MODEL_NAME`: video generation model name (optional, default `dreamina-seedance-2-5-260628`)

---

## 🔄 Resuming Unfinished Tasks (Checkpoint Resume)

> **When a new conversation starts or context is lost, you must first run this detection flow before deciding whether to create a new task or continue an existing one.**

### Resume Detection Flow

**Step one: list existing task directories**

```bash
python scripts/task_manager.py list
```

If existing task directories are found, check the completion status of their artifacts.

**Step two: inspect artifacts and determine the resume point**

Enter the most recent task_folder and use the following rules to determine which step to resume from:

| Existing Artifacts | Missing Artifacts | Resume at Step |
|---------|---------|-----------|
| No artifacts at all | All | Step 2: initialize task directory |
| `requirements.md` | `plot.md`, `script.md` | Step 3: screenplay generation |
| `plot.md`, `script.md` | `characters/` | Step 4: character design |
| `characters/`, `characters.md` | `storyboard/` | Step 5: scene art |
| `storyboard/` has storyboard images | `videos/` | Step 6: storyboard video |
| `videos/` has video files | `final/` | Step 7: video synthesis |
| `final/` has final video | Scoring report | Step 8: artifact verification |

**Step three: load context from existing artifacts**

If continuing from an intermediate step, **you must first read the completed artifact files** to restore context:
- Read `characters.md` to restore the STYLE_ANCHOR and character descriptions
- Read `plot.md` to restore the plot outline and duration allocation
- Read `script.md` to restore the complete dialogue screenplay
- Read the TOS URL records already present in the task directory

**Step four: confirm with the user**

Show the detection results to the user:
- Show the completed steps and their corresponding artifacts
- Show the next step to be executed
- Ask the user whether to continue this task or start a new one

> ⚠️ **If the user provides a brand-new story idea**, skip the resume flow and start directly from Step 1.
> Only run the resume flow when the user explicitly expresses intent such as "continue", "keep going", or "the previous one".

---

## Full Pipeline Overview

```
User story idea
  ↓
Step 0: Resume detection → python scripts/task_manager.py list (check for unfinished tasks)
Step 1: Read configuration → python scripts/app_config.py (smart duration mode, 4s~30s dynamic range)
Step 2: Initialize task directory → python scripts/task_manager.py init "<task_name>"
  ↓ ⚠️ Content safety pre-review (assess risk level, explain to user)
Step 3: Screenplay generation → python scripts/web_search.py research + write screenplay + smart duration allocation (see references/screenplay-generator.md)
Step 4: Character design → python scripts/image_generate.py generate character portraits (see references/character-designer.md)
Step 5: Scene art → python scripts/image_generate.py generate storyboard images (see references/scene-designer.md)
Step 6: Storyboard video → python scripts/batch_video.py submit/poll + independent duration per segment (see references/storyboard-director.md)
Step 7: Video synthesis → python scripts/video_merge.py + tos_upload.py (see references/video-synthesizer.md)
Step 8: Artifact verification and quality scoring → check artifact completeness item by item + generate scoring report
  ↓
Complete comic drama video + TOS signed link + scoring report
```

---

## Step 1: Read Startup Configuration

```bash
python scripts/app_config.py
```

The output JSON contains:
- `video_duration_minutes`: video duration (minutes)
- `total_seconds`: total seconds
- `smart_duration`: `true` (smart duration mode enabled)
- `duration_range`: `{"min": 4, "max": 30}` (selectable duration range per segment)
- `duration_options`: `"4s ~ 30s dynamic allocation"`
- `scene_count_range`: `{"min": N, "max": M}` (reference range for scene count)
- `recommended_scene_count`: recommended scene count (estimated at the midpoint average duration)

### Smart Duration Mode Explained

Each storyboard scene is assigned its own duration based on **the needs of the story's pacing** (continuously selectable from **4 seconds ~ 30 seconds**), rather than all using a uniform duration. **Duration diversity is the key to making the comic drama's rhythm come alive** — quick cuts create urgency, long takes build emotion, and alternating between them keeps the audience immersed in the story.

| Scene Type | Recommended Duration Range | Applicable Situations | Dialogue Density |
|---------|-------------|---------|---------|
| Tense quick cuts | **4~6 seconds** | Chase scenes, jump-scare moments, rapid flashbacks, montage transitions, one-hit kills | 1~2 short lines or pure visuals with no dialogue |
| Standard narrative | **7~10 seconds** | Opening setup, transitions, establishing environments, simple dialogue, closing afterglow | 3~5 lines of dialogue, standard pacing |
| Climax build-up | **11~15 seconds** | Ultimate showdowns, emotional outbursts, multi-character confrontations, key turning points, dense dialogue | 6~10 lines of dialogue, intense exchanges |
| Epic long take | **16~30 seconds** | Grand finales, extended one-shot battles, multi-phase showdowns, complete emotional arcs within a single scene | 10~16 lines of dialogue, or sustained spectacle with multi-phase action |

**The master director decides each chapter's duration during Step 3 (screenplay generation), based on the chapter's narrative function and pacing needs**, ensuring:
- Total duration ≈ `total_seconds` (±10% tolerance allowed)
- Climax chapters (Act Three) are prioritized for 11~15 seconds; the single most important showdown may use a 16~30 second epic long take
- Tense chases/flashbacks may use 4~6 second quick cuts
- Opening and closing chapters typically use 7~10 seconds
- **Adjacent scenes should vary in duration** — avoid multiple consecutive scenes of identical length, which makes the pacing monotonous

Continue after confirming the configuration with the user.

---

## Step 2: Initialize Task Directory

```bash
python scripts/task_manager.py init "<task_name>"
```

Extract core keywords from the story idea as the task_name. The script returns JSON:

```json
{
  "task_folder": "{COMIC_DRAMA_OUTPUT_DIR}/task_20260222_143000_keywords/",
  "storyboard_dir": "{COMIC_DRAMA_OUTPUT_DIR}/task_.../storyboard/",
  "characters_dir": "{COMIC_DRAMA_OUTPUT_DIR}/task_.../characters/",
  "videos_dir": "{COMIC_DRAMA_OUTPUT_DIR}/task_.../videos/",
  "final_dir": "{COMIC_DRAMA_OUTPUT_DIR}/task_.../final/",
  "outputs_dir": "{COMIC_DRAMA_OUTPUT_DIR}/",
  "deleted_tasks": []
}
```

Record all paths for use throughout the subsequent steps. FIFO auto-cleanup keeps at most 16 tasks.

> ⚠️ **Content safety pre-review**: after this step and before Step 3, perform a content safety pre-review of the user's story idea (see "Content Safety Review Reminder" above) and briefly explain the risk level to the user.

---

## Step 3: Screenplay Generation (with Smart Duration Allocation)

**For the complete specification, see `references/screenplay-generator.md`**.

Core workflow:
1. **In-depth research via `python scripts/web_search.py`** (must be done before writing the screenplay)
2. Save the requirements document `requirements.md`
3. Write a chapter-based plot outline `plot.md` (including a global style anchor declaration + emotional arc chart)
4. **Dynamically allocate a duration for each chapter** (4 seconds ~ 30 seconds, based on story pacing)
5. Write the complete dialogue screenplay `script.md` (each chapter annotated with its duration; the second-by-second script laid out according to actual duration)
6. Output the `scene_durations` list (for use in Step 6)

### Smart Duration Allocation Rules

When writing plot.md, annotate each chapter with its duration (dynamically chosen from 4s ~ 30s):

```
Chapter 1: [chapter name] (6 seconds) — [summary]    ← Rapid flashback/prologue, tight opening
Chapter 2: [chapter name] (8 seconds) — [summary]    ← World-building, standard narrative
Chapter 3: [chapter name] (5 seconds) — [summary]    ← Tense chase/crisis strikes, quick cuts
Chapter 4: [chapter name] (10 seconds) — [summary]   ← Conflict escalates, needs more dialogue
Chapter 5: [chapter name] (14 seconds) — [summary]   ← Climactic showdown, intense exchanges
Chapter 6: [chapter name] (12 seconds) — [summary]   ← Climax continues, emotional outburst
Chapter 7: [chapter name] (5 seconds) — [summary]    ← Ending afterglow, brief freeze-frame
```

**Duration allocation decision table**:

| Criteria (any one qualifies) | Recommended Duration Range |
|------------------------|-------------|
| Climactic showdown, ultimate confrontation | **12~15 seconds** |
| Multiple characters clashing simultaneously (3+) | **12~15 seconds** |
| Key plot turning point, twist reveal | **11~14 seconds** |
| Emotional outburst (furious roar, do-or-die declaration, dying words) | **11~15 seconds** |
| Dense dialogue (needs 6+ lines to express fully) | **11~15 seconds** |
| Complex action choreography (multiple consecutive action beats) | **12~15 seconds** |
| Grand finale, the story's decisive battle | **20~30 seconds** |
| Multi-phase showdown (2+ distinct phases in one scene) | **16~25 seconds** |
| Complete emotional arc in a single scene (build-up → eruption → aftermath) | **16~24 seconds** |
| Opening world-building | **7~10 seconds** |
| Transitions, environment changes | **6~9 seconds** |
| Simple dialogue (3-5 lines suffice) | **7~10 seconds** |
| Ending afterglow, emotional settling | **6~10 seconds** |
| Pure atmosphere building | **5~8 seconds** |
| Tense chase, crisis flashback, one-hit kill | **4~6 seconds** |
| Montage transition, dream flash | **4~5 seconds** |
| Jump-scare moment, sudden event | **4~5 seconds** |

> **Key principle**: duration diversity > duration uniformity. A good comic drama's rhythm should rise and fall like a heartbeat — short and punchy like drumbeats when tense (4~6s), gentle like strings during build-up (7~10s), long and sweeping like a symphony at the climax (11~15s), with an epic long take (16~30s) reserved for the grand finale.

**How each chapter's duration is reflected in script.md**:
- Chapter heading format: `## Chapter N: [chapter name] (Duration: Xs)` (X is an integer between 4~30)
- The second-by-second script timeline is laid out per actual duration (e.g. a 5-second scene: `0:00-0:05`; a 12-second scene: `0:00-0:12`)
- 11~15 second scenes have higher dialogue density (6-10 lines) and richer action choreography
- 16~30 second epic long takes have the highest dialogue density (10-16 lines) and multi-phase action choreography
- 7~10 second scenes have standard dialogue density (3-5 lines)
- 4~6 second scenes have minimal dialogue (0-2 lines), relying primarily on visual impact

**Confirm Step 3 artifacts**:
- `{task_folder}/requirements.md` ✅
- `{task_folder}/plot.md` ✅ (with chapter breakdown + per-chapter duration annotations + style anchor + emotional arc)
- `{task_folder}/script.md` ✅ (with dialogue, expressions, actions, scene bridging, ending states, **independent duration per chapter**)
- `scene_durations` list recorded ✅ (e.g. `[6, 8, 5, 10, 14, 12, 5]`)

Extract from plot.md: the list of main characters and the core visual style (default: Chinese anime 3D realistic style (国漫3D写实)).

**🔔 Show key outputs to the user** (must be shown after confirming artifacts and before moving to the next step):
- 📖 **Plot outline**: show the complete chaptered outline from plot.md (chapter names + duration annotations + summaries)
- 🎭 **Dialogue excerpts per chapter**: show 1-2 of the most striking core lines from each chapter
- 📊 **Duration allocation summary table**: chapter — duration — allocation rationale
- 📈 **Emotional arc chart**: visualization of each chapter's emotional intensity
- 👥 **Character list**: main character names + roles + one-line summaries

---

## Step 4: Character Design

**For the complete specification, see `references/character-designer.md`**.

Core workflow:
1. Determine the visual style and generate the **STYLE_ANCHOR** (global style anchor string)
2. Craft precise English AI prompts for each character
3. ⚡ Use `python scripts/batch_image_generate.py` to **generate in parallel** the character portraits + cover image
4. Save the character design document `characters.md`
5. **Upload all portraits and the cover to TOS** and obtain TOS URLs (for image display)

**Keys to visual style consistency**:
- Write the STYLE_ANCHOR at the top of characters.md; all subsequent steps must reference it
- Once a character's English prompt is finalized, **reuse it verbatim** in all subsequent scenes — only appending actions/expressions is allowed
- Use precise English color words for the color scheme (e.g. `midnight blue` rather than `blue`)

Confirm artifacts:
- `{task_folder}/characters.md` ✅ (with STYLE_ANCHOR + English prompts + portrait images)
- Character portrait .jpg files exist under `{characters_dir}/` ✅
- `{task_folder}/cover.jpg` ✅
- All character portraits and the cover image uploaded to TOS, TOS URLs recorded ✅

**🔔 Show key outputs to the user**:
- 🎨 **STYLE_ANCHOR**: show the complete style anchor string
- 👤 **Character summaries**: a description of each character (name + role + signature traits)
- 🖼️ **Character portrait previews**: show all character portraits as Markdown images (⚠️ **must use TOS URLs, never local disk paths**)
- 🖼️ **Cover image preview**: show the cover image as a Markdown image (⚠️ **must use TOS URL**)

---

## Step 5: Scene Art (Storyboard Images)

**For the complete specification, see `references/scene-designer.md`**.

Core workflow:
1. Extract the STYLE_ANCHOR from characters.md
2. Build a prompt for each scene (beginning with the STYLE_ANCHOR, reflecting the scene's ending state)
3. ⚡ Use `python scripts/batch_image_generate.py` to **generate all storyboard images in parallel** (built-in automatic retries + simplified-prompt fallback on failure)
4. Upload to TOS and record the TOS URLs

**Keys to visual style consistency**:
- All storyboard image prompts must begin with the STYLE_ANCHOR
- Character descriptions must strictly reuse the English prompts from characters.md
- Adjacent scenes should keep color tone, lighting, and environmental elements visually coherent

**Scene generation failure fallback**:
- The script has built-in automatic retries (up to 3 per image)
- After all retries fail, it automatically tries again with a simplified prompt (removing high-risk terms)
- If it still fails, extract the failed scene's prompt, simplify it manually, and retry individually with `image_generate.py`

Confirm artifacts:
- scene_count storyboard images exist under `{storyboard_dir}/` ✅
- TOS URLs for all storyboard images recorded ✅ (for use in Step 6)

**🔔 Show key outputs to the user** (⚠️ **storyboard images must be shown — do not skip**):
- 🖼️ **Storyboard image previews**: show all storyboard images as a Markdown image list (⚠️ **use TOS URLs**), each accompanied by:
  - The corresponding chapter name
  - A one-line scene description
  - The chapter's duration annotation
- 📊 **Generation statistics**: total / succeeded / elapsed time

---

## Step 6: Storyboard Video Generation (Smart Duration)

**For the complete specification, see `references/storyboard-director.md`**.

Core workflow:
1. Extract the STYLE_ANCHOR from characters.md
2. Build a seven-dimension director-grade video prompt for each scene (beginning with the STYLE_ANCHOR)
3. **Prepare the list of independent durations for each video segment** (taken from Step 3's `scene_durations`, dynamic values of 4~30 seconds)
4. Submit video tasks in batch (with first-frame TOS URLs + independent duration per segment)
5. Poll until all tasks complete
6. Download the videos + quality scoring

### Smart Duration Submission

Write the prompts list, first-frame URL list, and durations list into separate JSON files, then call submit:

**Step one: prepare the JSON files (⚠️ strictly follow the formats in the quick reference table at the top of this file)**

```json
// prompts.json — ⚠️ must be a plain string array, NOT an array of objects!
[
  "STYLE_ANCHOR, environment for scene 1, character desc, action, dialogue, camera, audio",
  "STYLE_ANCHOR, environment for scene 2, character desc, action, dialogue, camera, audio"
]

// frames.json — array of TOS URL strings (one-to-one with prompts)
[
  "https://tos-ap-southeast-1.bytepluses.com/.../scene_01.jpg?<signature params>...",
  "https://tos-ap-southeast-1.bytepluses.com/.../scene_02.jpg?<signature params>..."
]

// durations.json — integer array (one-to-one with prompts)
[6, 8, 5, 10, 14, 12, 5]
```

**Step two: call the submit command**

```bash
python scripts/batch_video.py submit \
  --prompts-file prompts.json \
  --first-frames-file frames.json \
  --durations-file durations.json
```

**Step three: save the `submitted` field from the result as task_ids.json**

Submit return format:
```json
{
  "submitted": {"scene_01": "task_id_xxx", "scene_02": "task_id_yyy"},
  "errors": {},
  "total": 7
}
```

Save the contents of the `submitted` field as `task_ids.json`:
```json
{"scene_01": "task_id_xxx", "scene_02": "task_id_yyy"}
```

> ⚠️ **The uniform-duration `--duration` parameter is no longer used**; use `--durations-file` instead to give each segment an independent duration.
> The durations list in `durations.json` must correspond one-to-one with `prompts.json`, and each value must be an integer between 4~30.

**Keys to visual style consistency**:
- All video prompts begin with the STYLE_ANCHOR
- Character descriptions strictly reuse the English prompts from characters.md
- Dialogue is extracted verbatim from script.md
- 11~15 second scenes: at least 5-6 lines of dialogue, with an intense back-and-forth rhythm
- 16~30 second scenes: at least 8-10 lines of dialogue, structured in multiple phases so the long take never stalls
- 7~10 second scenes: at least 3-4 lines of dialogue
- 4~6 second scenes: 0-2 minimal lines of dialogue, relying primarily on visual impact
- Diversify camera work — adjacent scenes must not use exactly the same camera technique

### Professional Guide to Camera Language

**The camera is the director's most important storytelling tool**. Different emotions require distinctly different camera strategies:

#### Camera Strategies for Tense/Suspenseful Scenes

| Camera Technique | Description | Emotional Effect |
|---------|------|---------|
| Continuous push from medium to close-up | `medium shot slowly pushing in to extreme close-up on eyes` | Escalating pressure, hinting at approaching danger |
| Rapid shot-reverse-shot | `rapid shot-reverse-shot between characters, each cut 0.5s` | Psychological standoff at white heat, maximum tension |
| Handheld shaky camera | `handheld shaky camera, slight vibration, unstable framing` | Instability; the audience inhabits the character's fear |
| Dutch angle | `tilted camera 15-25 degrees, off-balance composition` | A world out of order, psychological distortion |
| Telephoto depth compression | `telephoto lens compression, blurred foreground and background` | Isolates the character, compresses space, suffocating feel |
| Negative space in shadow | `deep shadows consuming 60% of frame, character half-lit` | Unknown threat, atmosphere of dread |

#### Camera Strategies for Climax/Outburst Scenes

| Camera Technique | Description | Emotional Effect |
|---------|------|---------|
| Speed ramp | `normal speed → ultra-slow 0.2x on impact → snap back to real-time` | Visual emphasis on the decisive strike |
| 360-degree orbit | `360-degree orbit around character during energy release` | Ritualistic grandeur of the energy burst |
| Extreme low angle | `extreme worm's-eye view looking up, silhouette against sky` | Overwhelming presence, epic feel |
| Tracking shot | `dynamic tracking shot racing alongside the action, camera tilting 45°` | Immersion in the action |
| Rapid montage | `rapid montage: face → fist → impact → reaction, 0.3s per cut` | Explosive combat rhythm |
| Whip pan | `whip pan from attacker to defender, motion blur, freeze on impact` | Sense of ambush, transfer of force |

#### Camera Strategies for Emotional Build-up Scenes

| Camera Technique | Description | Emotional Effect |
|---------|------|---------|
| Slow dolly long take | `slow steady dolly push-in over 5 seconds, minimal movement` | Emotion seeps in; the audience is slowly drawn into the frame |
| Wide shot to character | `wide establishing shot slowly narrowing to medium shot on character` | Smallness → focus → empathy |
| Close-up on micro-expressions | `extreme close-up held for 3 seconds, capturing every micro-expression` | Silence speaks louder than words; emotion transmitted |
| Over-the-shoulder shot | `over-the-shoulder shot, shallow depth of field, speaker in soft focus` | Psychological distance of intimacy/confrontation |
| Slow pull-back | `slow pull-back revealing vast landscape, character becoming small` | Loneliness, sense of fate, lingering afterglow |
| Static locked-off | `static locked-off camera, subject slowly walking away, held 6 seconds` | Ending afterglow, emotional settling |

> **Camera rhythm rules**: tense scenes use quick cuts (a cut every 0.5~1.5s), build-up scenes use long takes (3~6s without cutting), climax scenes go slow-fast-slow (build-up → burst → aftermath).

**Keys to dialogue and continuity**:
- No more than 4 seconds between lines of dialogue; keep a sense of back-and-forth
- Audio emotion matches visual emotion; music transitions smoothly between adjacent scenes
- The environment stays consistent across consecutive scenes, varying only in degree of destruction/lighting

Confirm artifacts:
- scene_count .mp4 files exist under `{videos_dir}/` ✅
- Each video segment contains Chinese dialogue audio + music + sound effects ✅
- Each segment's duration matches `scene_durations` ✅

**🔔 Show key outputs to the user** (⚠️ **every storyboard video segment must be shown — do not skip**):
- 🎬 **Storyboard video list**: all videos **must** be shown in the format `<video src="{tos_url}" width="640" controls>Chapter N {chapter name}</video>` (⚠️ **must use TOS URLs — never local disk paths, plain-text links, or Markdown links**), each accompanied by chapter name + duration + a 1-2 line excerpt of core dialogue
- 📊 **Quality scores**: show the scoring results

> ⚠️ Video display format example (must be followed strictly):
> ```
> **Chapter 1: {chapter name}** ({duration} seconds)
> Core dialogue: "{Character A}: {line}"
> <video src="https://tos-ap-southeast-1.bytepluses.com/.../scene_01.mp4?<signature params>" width="640" controls>Chapter 1 {chapter name}</video>
> ```

---

## Step 7: Video Synthesis and Delivery

**For the complete specification, see `references/video-synthesizer.md`**.

Core workflow:
1. **Check for and install ffmpeg** (installed automatically on first use)
2. Strictly filter video files (only accept the scene_NN.mp4 format)
3. Merge all videos in order
4. Upload to TOS
5. Save the delivery document and show the final result

**⚠️ Step one: check for and install ffmpeg (must confirm availability before synthesis)**

> 💡 **Explain to the user**: while checking/installing ffmpeg, briefly explain:
> "Next, the storyboard video segments need to be merged in order into one complete comic drama. Merging videos requires **ffmpeg** (an open-source audio/video processing tool); let me check whether it is already installed in the environment..."
> If installation is needed, inform the user: "Installing ffmpeg — a professional video-splicing tool used to seamlessly merge the {scene_count} storyboard video segments into the complete comic drama video, while automatically detecting the final duration. Installation takes only a few seconds."

```bash
# Check whether ffmpeg is installed
which ffmpeg && ffmpeg -version || echo "ffmpeg not found, installing..."

# macOS auto-install
brew install ffmpeg 2>/dev/null || true

# Linux auto-install
# sudo apt-get install -y ffmpeg 2>/dev/null || sudo yum install -y ffmpeg 2>/dev/null || true
```

> If ffmpeg is already installed, skip this — no need to reinstall.

**Merge the videos:**
```bash
python scripts/video_merge.py --input-dir "<videos_dir>" --output "<final_dir>/<task_name>_final.mp4" --scene-count <N>
python scripts/tos_upload.py "<final_dir>/<task_name>_final.mp4"
```

> The actual total duration after merging is detected automatically by ffprobe (since each segment's duration may differ).

Confirm artifacts:
- `{final_dir}/{task_name}_final.mp4` ✅
- TOS signed URL ✅

**🔔 Show key outputs to the user** (⚠️ **videos must be shown using the `<video>` tag — never plain-text links or Markdown links**):
- 🎬 **Final video**: the merged video **must** be shown in the format `<video src="{tos_signed_url}" width="640" controls>Complete comic drama video</video>` (⚠️ **must use the TOS URL; plain-text URLs, URLs wrapped in Markdown code blocks, and Markdown link format are forbidden**)
- 🔗 **TOS link**: show the complete signed URL (as a fallback text link, placed after the `<video>` tag)
- 📁 **Task directory structure**: show the complete directory tree

> ⚠️ **Final video display format (must be followed strictly — no other display method allowed)**:
> ```
> 🎬 Comic drama generation complete!
> 
> <video src="https://tos-ap-southeast-1.bytepluses.com/.../task_name_final.mp4?<signature params>" width="640" controls>Complete comic drama video</video>
> 
> 🔗 TOS link: https://tos-ap-southeast-1.bytepluses.com/.../task_name_final.mp4?<signature params>
> ```
> ❌ **Incorrect examples (forbidden)**:
> - ~~```text\nhttps://...\n```~~ (wrapped in a code block)
> - ~~[video link](https://...)~~ (Markdown link)
> - ~~https://...~~ (plain-text URL)

---

## Step 8: Artifact Verification and Quality Scoring

**After each task completes, full artifact verification and quality scoring must be performed.**

### 8.1 Artifact Completeness Check

Check the following artifact directory structure item by item, confirming that every file/folder **exists and is non-empty**:

```
{task_folder}/
├── characters/                  ← Must contain at least 1 .jpg file
│   ├── char_<name1>.jpg
│   ├── char_<name2>.jpg
│   └── char_<name3>.jpg
├── characters.md                ← Must be non-empty, with STYLE_ANCHOR + character prompts
├── cover.jpg                    ← Must exist with file size > 0
├── final/                       ← Must contain 1 _final.mp4 file
│   └── <task_name>_final.mp4
├── plot.md                      ← Must be non-empty, with chapter outline + duration allocation
├── requirements.md              ← Must be non-empty, with requirements document
├── script.md                    ← Must be non-empty, with second-by-second script
├── storyboard/                  ← Must contain scene_count .jpg files
│   ├── scene_01.jpg
│   ├── scene_02.jpg
│   └── ...
└── videos/                      ← Must contain scene_count .mp4 files
    ├── scene_01.mp4
    ├── scene_02.mp4
    └── ...
```

**Verification rules**:
- If any folder is empty or any file's content is empty → **the current task is judged a failure**
- File counts must strictly match scene_count (storyboard/ and videos/ directories)
- The file count under characters/ must match the number of main characters

### 8.2 Quality Scoring

Use the scoring tool to evaluate the task's quality:

```bash
python scripts/video_scorer.py "<task_folder>"
```

The scoring output covers 5 dimensions (each scored 0-10):

| Scoring Dimension | Scoring Criteria |
|---------|---------|
| Plot coherence | Whether scenes flow smoothly into one another, without a sense of disjointedness |
| Dialogue richness | Whether characters have enough lines, varied tone, and a sense of conflict |
| Visual quality | Consistency of visual style, quality of effects, use of camera work |
| Emotional tension | Whether there are dramatic ups and downs, and whether the climax lands with impact |
| Audio-visual sync | Whether the music fits the emotion and the voice-over is clear |

### 8.3 Artifact Verification Report Format

```
📋 Artifact Verification Report

├── characters/          {N} files  ✅/❌
├── characters.md        {size} chars   ✅/❌
├── cover.jpg            {size}KB   ✅/❌
├── final/               {N} files  ✅/❌
│   └── xxx_final.mp4    {size}MB   ✅/❌
├── plot.md              {size} chars   ✅/❌
├── requirements.md      {size} chars   ✅/❌
├── script.md            {size} chars   ✅/❌
├── storyboard/          {N} files  ✅/❌
└── videos/              {N} files  ✅/❌

Artifact completeness: ✅ All passed / ❌ {N} items missing

📊 Quality Scores
Plot coherence:      X/10
Dialogue richness:   X/10
Visual quality:      X/10
Emotional tension:   X/10
Audio-visual sync:   X/10
Overall score:       X.X/10

Improvement suggestions: [specific suggestions]
```

> **If any artifact is missing or empty, the entire task is judged a failure** — the specific missing items must be reported and their repair coordinated.

---

## Master Director Execution Rules

1. **Content safety pre-review**: after Step 2, a content safety pre-review of the story idea must be performed, with the risk level explained to the user
2. **Context passing**: every step must explicitly specify all path parameters and content parameters
3. **Quality gating**: after each step, confirm the artifacts exist; on anomalies, coordinate a fix before continuing
4. **Visual style consistency**: the STYLE_ANCHOR runs through the entire pipeline — all image/video prompts begin with it
5. **Character consistency**: the English prompts in characters.md are reused verbatim in all scenes
6. **Plot coherence**: scene bridging ensures natural transitions between adjacent chapters, and the emotional arc has a beginning, development, climax, and resolution
7. **Dialogue density**: 0-2 lines for 4~6 second scenes, at least 3 lines for 7~10 second scenes, at least 6 lines for 11~15 second scenes, at least 10 lines for 16~30 second scenes; no more than 4 seconds between lines, with a sense of back-and-forth
8. **Smart duration**: each chapter's duration is dynamically allocated from 4~30 seconds based on story pacing; duration diversity takes priority; total duration stays within the target range
9. **Camera diversity**: adjacent scenes must not repeat camera techniques; at least 5 camera-work types across the whole film; tense scenes use quick-cut close-ups, build-up scenes use slow long-take push-ins, climax scenes use speed ramps and orbits
10. **Video generation tools**: only `batch_video.py` submit/poll is allowed (or `create_video_task.py` + `query_video_task.py` for failure retries)
11. **Zero URL modification**: all image and video URLs must remain strictly in their original form throughout input and output — no tampering of any kind is allowed (including but not limited to modifying the domain, path, query parameters, or anchors).
12. **Output directory**: all outputs are fixed under `COMIC_DRAMA_OUTPUT_DIR` (default `./output/`), with an independent directory per task
13. **Image generation**: prefer `python scripts/batch_image_generate.py` for batch parallel generation (Step 4 character portraits, Step 5 storyboard images); use `python scripts/image_generate.py` for supplementary single images
14. **Content-safe wording**: avoid directly using high-risk terms like war/gore/weapons in video prompts; use euphemistic substitutes
15. **Artifact verification**: after Step 7 completes, the Step 8 artifact completeness check and quality scoring must be performed; any missing artifact means the task is judged a failure
16. **Show key outputs**: after each step completes, the step's key outputs (document summaries, image previews, video links, scoring reports, etc.) **must** be shown directly to the user rather than only returning file paths. The user should clearly see the plot outline, character portraits, **storyboard images**, videos, and other core outputs in the conversation flow
17. **Storyboard images must be shown**: after Step 5 completes, all storyboard image previews **must** be shown in Markdown image format (using TOS URLs), so the user can confirm the visuals before proceeding to video generation
18. **Video display format**: all videos (storyboard videos and the final merged video) **must** be shown using the `<video src="{tos_url}" width="640" controls>description</video>` format. Plain-text URLs, URLs wrapped in Markdown code blocks, and Markdown link format are **forbidden**
19. **Install ffmpeg on demand**: check for and install ffmpeg before Step 7 (video synthesis) begins; installing on demand avoids disrupting the earlier creative stages
20. **Scene generation fallback**: when storyboard image generation fails, retry automatically (up to 3 times); after retries fail, simplify the prompt and try again, ensuring as many scenes as possible generate successfully

## What Makes a Good Comic Drama

> The plot has a beginning, development, climax, and resolution; the lines and language have well-judged tension and release; the camera work is just right (varied camera techniques that draw the user into the world of the comic drama);
> the visuals are richly layered, the plot coherent, the emotions full, the characters distinctive; the visuals, scenes, music, and dialogue are refined and consistent;
> the visual style stays unified throughout, so that watching the comic drama the user can feel the pull of the story, the continuity of the plot, the tension of the protagonist, and the swell of the storyline.
> **Rhythm is the soul of a comic drama** — quick cuts tense like drumbeats (4~6s), narrative gentle like strings (7~10s), climaxes long and sweeping like a symphony (11~15s), epic finales in sustained long takes (16~30s);
> alternating among the three lets the audience's heartbeat rise and fall with the picture — that is masterful command of rhythm.
