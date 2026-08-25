# TODO Items

Housekeeping tasks to carry out as part of improvements to the codebase. 

- [ ] Remove the `llm_client` exclude workaround in agent.py once google-adk stops
      leaking the live client into `/dev/apps/{app}/build_graph`. Still needed as of
      google-adk 2.2.0 — it is not specific to the old 1.32.0 pin. Recheck by
      commenting the block out and loading the Dev UI; a 500 on `build_graph` means
      it is still required.
- [ ] Remove the `_parse_tool_call_arguments` json-repair workaround in agent.py
      once google-adk can tolerate malformed tool-call JSON from the model
      (unescaped quotes inside prompt strings). Still needed as of google-adk
      2.6.2 — the model error otherwise aborts the whole workflow run with a
      `json.decoder.JSONDecodeError`.
- [ ] Remove the `read_file_to_bytes` timeout wrapper in agent.py once veadk stops
      fetching generated media with an untimed, synchronous `requests.get()` on the
      event-loop thread (a single stalled download otherwise freezes the whole
      server). Still present as of veadk-python 1.0.9.
