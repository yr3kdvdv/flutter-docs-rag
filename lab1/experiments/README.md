# experiments/

[Research report](report.md) · [Protocol](protocol.md) · [Final selection](selection.md)

`configs/` contains the stage 06 variants. Each `runs/s06-*` directory contains
the exact config, raw attempts, aggregates and run metadata. The earlier run IDs
belong to the stage 05 smoke tests on the draft dataset. `evidence/stage06/`
contains the offline analysis, threshold replays, index build records and
identifier-and-score readback from Langfuse.

From `lab1/`, run the offline reproducer to verify the stored metrics:

```sh
uv run python experiments/analyze.py --final experiments/runs/s06-*-dev experiments/runs/s06-final-test
```
