# judge prompt versions

Never edit a published version: run metadata references the judge prompt by version and sha256.

- v1 (stage 05) — first version. Scores correctness (vs the reference answer) and faithfulness
  (vs the excerpts the generator received) on 1–5 with a short reason written first.
  Used with Gemini structured output at temperature 0; the judge model is recorded in meta.json.
