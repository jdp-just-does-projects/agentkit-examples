# AgentKit Examples

**Latest Update: 2026-08-28**

Welcome! This repository contains example AI agents written in Python and designed to run on AgentKit. Most of the examples here are stolen shamelessly from [agentkit-samples](https://github.com/bytedance/agentkit-samples), an official set of examples put together by developers at ByteDance.

AgentKit is available in two places: 

- [Volcano Engine](https://www.volcengine.com/) (火山引擎): ByteDance's Chinese cloud platform (for Mainland China)
- [BytePlus](https://www.byteplus.com/): ByteDance's international cloud platform (for the rest of the world - including Hong Kong, Macau, and Taiwan)

## Structure

We maintain separate sets of examples for each cloud platform:

- The `byteplus` folder contains examples tested on BytePlus
- The `volcengine` folder contains examples tested on Volcano Engine

We need to do this because of differences in:

- Product / feature availability
- Product / resource ID naming conventions
- API endpoint addresses
- Supported regions

This requires us to carefully test that a given example actually works on the target platform (Volcano Engine or BytePlus) and adjust accordingly.

## Included Demos

**Note: Subfolders are under `byteplus/` or `volcengine/`** 

| Subfolder | Agent Name | BytePlus support | VolcEngine support | Summary |
|------|------------|:----------------:|:------------------:|---------|
| `ad_video_gen` | `ad_video_gen` | ✅ | ✅ | Single-agent marketing video generator: turns product info into a 9:16 short video via a storyboard reference image. |
| `ad_video_gen_seq` | `ad_video_gen_seq` | ✅ | ✅ | Sequential multi-agent pipeline that plans, generates, evaluates, and stitches marketing shot videos. |
| `comic_drama_gen` | `comic_drama_master` | ✅ | ✅ | Turns a story idea into a complete comic drama video, from screenplay to storyboard to merged final video. |
| `coding_coach_harness` | `code-coach` | ✅ | ✅ | No-code **AgentKit Harness** sample: a coding-exercise trainer defined entirely in `harness.yaml` + a Skill Hub skill, which runs trainee submissions against hidden tests in a CodeEnv sandbox and scores them. Uses the standalone `agentkit` CLI (see its README). |
| `sandbox_demo` | `sandbox_web_coder` | ✅ | ✅ | Cloud coding agent showcasing the AgentKit AIO Sandbox: writes and tests web projects entirely inside the sandbox, then delivers the code as a TOS download link. |
| `video_gen` | `storybook_illustrator` | ✅ | ✅ | Turns children's stories into 3D cartoon storybook illustrations and a merged storyboard video. |

## Licensing

Because many of these are very close copies of of the AgentKit samples located in the [agentkit-samples](https://github.com/bytedance/agentkit-samples) repository, I preserve the license used there, which is the [Apache 2.0](https://github.com/bytedance/agentkit-samples/blob/main/LICENSE) license.

I have also borrowed the `.gitleaks.toml` and `.gitignore` files from that repository, to ensure consistency in what is checked in.

The `coding_coach_harness` example is a port of [`harness_code_coach`](https://github.com/windrichie/byteplus-agentkit-samples/tree/main/use-cases/harness_code_coach) from Windrichie's [byteplus-agentkit-samples](https://github.com/windrichie/byteplus-agentkit-samples) repository, included here under the same Apache 2.0 license with attribution in its README.
