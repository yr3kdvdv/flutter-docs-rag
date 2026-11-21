# flutter-qa-v1 — evaluation dataset (DRAFT)

45 questions about the official Flutter documentation, labelled on the fixed corpus snapshot
`flutter/website@4fee0255ef9f0c85f6dd37513bf659613f57e5eb` (`configs/full.yaml`).
Schema and rules: `docs/contracts/stage05.md` §5.1; loader and validator:
`src/flutter_rag/evaluation/{dataset,check}.py`.

**Status: every item is `draft`.** The items were written by one agent (evaluation-engineer,
Claude subagent, 2026-11-06). Nobody has checked them independently yet. They must not be
marked `agent_checked` or `verified` until that check is done (see "Status" below).

| file | items | use |
|---|---|---|
| `dev.jsonl` | 15 | tuning and comparing configurations (stage 06) |
| `test.jsonl` | 30 | final hold-out; opened only with `flutter-rag evaluate --final` (N03) |

## Distribution (type × split × language)

| type | dev ru | dev en | test ru | test en | total ru / en |
|---|---|---|---|---|---|
| factoid | 2 | 1 | 3 | 3 | 5 / 4 |
| multi_doc | 2 | 1 | 3 | 3 | 5 / 4 |
| lookup | 1 | 2 | 3 | 3 | 4 / 5 |
| contextual | 1 | 2 | 3 | 3 | 4 / 5 |
| unanswerable | 2 | 1 | 3 | 3 | 5 / 4 |
| **all** | **8** | **7** | **15** | **15** | **23 / 22** |

Gold labels point to 34 different documents in many areas: deployment (Android, obfuscation,
flavors), web (Wasm, URL strategies), platform integration (predictive back, deep links),
performance (Impeller, isolates), testing, accessibility, i18n, state management, architecture,
tools (hot reload, Widget Previewer), Swift Package Manager, add-to-app, security.

## Question types

- **factoid** — one short fact stated in one section (a version, a limit, yes/no + reason).
- **multi_doc** — the answer needs facts from at least two different pages
  (`gold_documents` has ≥ 2 entries).
- **lookup** — find a specific identifier: a command, a config key, an annotation, a manifest
  attribute; usually has `expected_code`.
- **contextual** — a developer describes a situation or a symptom ("hot reload does not show my
  change", "404 after refresh on nginx"); the answer requires mapping the situation to the right
  part of the documentation and explaining it.
- **unanswerable** — a plausible Flutter question whose answer is not in the corpus. The system
  must refuse (`insufficient_context`). Absence was checked by a case-insensitive substring
  search over all 647 cleaned `ok` documents of the snapshot; the searched terms are in
  `notes` as `absent_terms: [...]`, and `dataset-check` re-runs this search.

Questions are phrased the way a developer would ask, not copied from headings. Russian
questions keep API names in Latin script, as Russian-speaking developers write them.

## How it was built

1. The manifest `data/manifests/full/latest.json` and the raw blobs of the snapshot were read
   (read-only) from the integrator's ingest.
2. Every `ok` page was cleaned exactly like `pipeline.ingest` does (`clean_markdown` with the same
   include resolver over the manifest `includes`, see `evaluation/check.py::clean_document`);
   section ids came from `chunking.document_section_ids` (`"<document_id>#<anchor>"`).
3. Questions were drafted from the real cleaned text. `supporting_excerpts[].text` are copied
   verbatim from the cleaned page and must lie inside the named section.
4. `expected_answer` is a short reference written from those excerpts; `must_include` holds only
   language-neutral identifiers/numbers that a correct answer in either language should contain
   (checked case-insensitively); `expected_code` is checked ignoring whitespace.
5. `uv run flutter-rag dataset-check` validates everything against the snapshot.

Known weak spots for the independent check: a few `must_include` entries are weak (for example
`"5"` for "5 working days"); some pages are used by more than one item (obfuscation, hot reload,
Wasm, URL strategies, SwiftPM, app links); `expected_answer` reflects one author's reading.

## Status values

- `draft` — written, validated by `dataset-check` only (all 45 items now).
- `agent_checked` — re-read against the source text by a separate Claude subagent (not an
  independent check).
- `verified` — checked by Codex/Gemini or by the student.

## Leakage rules

The dataset is never indexed: the corpus comes only from GitHub `flutter/website`
(`corpus.repo`), and `tests/test_evaluation_dataset.py::test_n04_*` checks that no `corpus.include`
pattern of any `configs/*.yaml` can match a file under `lab1/evaluation/`.
Do not tune anything on `test.jsonl`.
