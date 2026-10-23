# Evidence — stage 03 (vertical slice)

All runs are real: GitHub, Gemini API (free tier), embedded Qdrant, Langfuse Cloud EU.
Offline tests with fakes are in `lab1/tests` and are not part of this evidence.

## final/ — code commit `7cac4ca`, clean tree (`git_dirty: False` in every trace)

Config `lab1/configs/slice.yaml` (`slice-v1`), corpus `flutter/website@3eb87869bb0d`, 8 pages,
embeddings `gemini-embedding-001@768`, LLM `gemini-3.5-flash-lite`, prompt `answer/v1.2`.
Local `data/raw`, `data/cache`, `data/index` were deleted before `ingest-1`.

| File | What it shows | Trace |
|---|---|---|
| ingest-1-from-scratch.json | 11 files downloaded, 144 chunks, 9 embedding calls, limiter wait 54 s, 0 retries | d966b328f8f7854fa85929f59d750b6c |
| ingest-2-rerun.json | 0 downloads, 0 embedding calls, still 144 points (idempotent) | 47b77ddcde745237265e8f881f8ca2d5 |
| ask-1-in-corpus-ru.json | answered in Russian, sources = constraints page | e2c97be2c40fe72b5fe6a5034d945e16 |
| ask-2-out-of-corpus-ru.json | insufficient_context (FCM is not in the 8 pages), no sources | b0fef497d5e85746a59c6c94dbfdefaa |
| ask-3-in-corpus-en.json | answered with code copied from fetch-data, 3 sources | 9411244585f659726f4db21a06afa493 |
| ask-4-upstream-invalid-key.json | `GEMINI_API_KEY=invalid…` for one command: upstream_error/auth, exit 4, no retries | e646547efc489a60cc41745bf292f274 |
| trace-*.json | each trace read back by `flutter-rag trace-show` in a separate process | — |

Langfuse URL pattern: `https://cloud.langfuse.com/project/cmvl28r6600z6ad0kmhvny3nt/traces/<trace_id>`
(project is private; open while logged in).

## dev-runs/ — runs on uncommitted code during development (`git_dirty: True`)

Kept because they document defects found and fixed in this stage:
- `ask-in-corpus-prompt-v1-english-defect.json` — prompt v1 answered a Russian question in English.
- `ask-out-of-corpus-prompt-v1.1-english-refusal.json` — v1.1 still refused in English.
- `source-links-check.txt` — all 144 `url#anchor` exist on docs.flutter.dev after the anchor fix
  (before it, 6 chunks pointed to missing anchors).
- `api-ask.json` — `POST /ask` on a real `flutter-rag serve`; a concurrent CLI got exit 3 (lock).
