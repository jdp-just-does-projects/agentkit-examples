# TODO Items

Housekeeping tasks to carry out as part of improvements to the codebase.

- [ ] agent.py still uses the deprecated `Agent(skills=..., skills_mode="local")`
      loading path (veadk 1.0.9 logs a deprecation warning suggesting
      `google.adk.skills.load_skill_from_dir` / `SkillToolset`). Migrate when the
      legacy path is removed.
- [ ] The skill's `web_search.py` signs requests against the Volcano Engine
      torchlight endpoint (`mercury.volcengineapi.com`). It currently also accepts
      BytePlus credentials, but a BytePlus-native search API would be more correct
      for a future byteplus/ port of this example.
