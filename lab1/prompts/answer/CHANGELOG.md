# answer prompt versions

Never edit a published version: traces reference prompts by version and sha256.

- v1 (stage 03) — first version.
- v1.1 (stage 03) — fixes a defect seen in trace 043adb1524f60071e059dfd7250dd5c3: a
  Russian question was answered in English. Rule 4 now states the language explicitly.
  This is a bug fix, not one of the two prompt variants to be compared in stage 05/06.
- v1.2 (stage 03) — same defect for refusals (trace 86a9d232cc799983c798239cada32a38: Russian
  question, English refusal). Rule 2 now also requires the language of the question.
- (stage 04, no new prompt version) v1.2 still refused in English to Russian questions
  (Codex review F6; 3 of 3 FCM runs on 2026-11-04). The refusal text shown to the user is now
  produced by code from the question language (`pipeline.REFUSAL_TEXT`); the prompt is unchanged.
- (stage 04b, no new prompt version) the language detector ignores quoted text and code spans
  (re-verification finding G1). Prompt unchanged.
