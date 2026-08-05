# AgentKit Examples

**Latest Update: 2026-08-04**

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

## Licensing

Because many of these are very close copies of of the AgentKit samples located in the [agentkit-samples](https://github.com/bytedance/agentkit-samples) repository, I preserve the license used there, which is the [Apache 2.0](https://github.com/bytedance/agentkit-samples/blob/main/LICENSE) license.

I have also borrowed the `.gitleaks.toml` and `.gitignore` files from that repository, to ensure consistency in what is checked in.
