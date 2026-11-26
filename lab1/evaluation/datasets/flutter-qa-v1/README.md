# flutter-qa-v1 — verified evaluation dataset

45 questions about the official Flutter documentation, labelled on the fixed corpus snapshot
`flutter/website@4fee0255ef9f0c85f6dd37513bf659613f57e5eb` (`configs/full.yaml`).
Schema and rules: `docs/contracts/stage05.md` §5.1; loader and validator:
`src/flutter_rag/evaluation/{dataset,check}.py`.

**Status: all 45 items are `verified`.** The dataset was drafted by the Claude evaluation-engineer
subagent. Codex independently reviewed the draft at `af6ab74` on 2026-11-26. The accepted revision
applies the recommendations for 29 items and keeps the content of the other 16 items.
[Independent review](../../../../docs/reviews/dataset-check.md)

| file | items | use |
|---|---|---|
| `dev.jsonl` | 15 | tuning and comparing configurations (stage 06) |
| `test.jsonl` | 30 | final evaluation with `flutter-rag evaluate --final` (N03) |

## Accepted revision

Use these SHA-256 hashes to pin the inputs for stage 06. The stage 05 smoke runs used the draft.

| File | SHA-256 |
|---|---|
| `dev.jsonl` | `df6fb5d791a9b7889591d71d65b33a1e9f1ea49ea89dedc97e3e21f240d1100a` |
| `test.jsonl` | `680ba531b37b71ba725796a75ea541ac8092845a59de704110cf15794426f2eb` |

The validator passed on the pinned corpus with 82 excerpts, 51 gold sections and 30 absence terms.
All 51 sections were found in both full-corpus Qdrant collections. The offline dataset test checks
each reference answer against its own `must_include` and `expected_code` markers.

## Distribution (type × split × language)

| type | dev ru | dev en | test ru | test en | total ru / en |
|---|---|---|---|---|---|
| factoid | 2 | 1 | 3 | 3 | 5 / 4 |
| multi_doc | 2 | 1 | 3 | 3 | 5 / 4 |
| lookup | 1 | 2 | 3 | 3 | 4 / 5 |
| contextual | 1 | 2 | 3 | 3 | 4 / 5 |
| unanswerable | 2 | 1 | 3 | 3 | 5 / 4 |
| **all** | **8** | **7** | **15** | **15** | **23 / 22** |

Gold labels point to 31 different documents in areas including deployment (Android, obfuscation,
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
4. `expected_answer` is a short reference based on those excerpts. `must_include` checks literal
   markers case-insensitively. `expected_code` checks a substring after removing whitespace.
   The judge and manual review assess facts that need semantic comparison, such as dates,
   units and equivalent formulations.
5. Run `uv run flutter-rag dataset-check` to validate the schema, distribution, exact quotes,
   gold section IDs and recorded absence terms against the snapshot.

## Status values

- `draft` — written and validated by `dataset-check`.
- `agent_checked` — re-read against the source text by a separate Claude subagent.
- `verified` — checked by Codex/Gemini or by the student.

## Leakage rules

The dataset is never indexed: the corpus comes only from GitHub `flutter/website`
(`corpus.repo`), and `tests/test_evaluation_dataset.py::test_n04_*` checks that no `corpus.include`
pattern of any `configs/*.yaml` can match a file under `lab1/evaluation/`.
Do not tune anything on `test.jsonl`.
