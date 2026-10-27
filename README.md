# EditSlice

Pack the functions a bug report points at, under a token budget. On 280 SWE-bench Lite fixes that land inside a function, reading BM25's files from the top contains the edit 21 times in 1024 tokens. Opening the top five files and packing functions inside them contains it 68 times. Packing function spans from BM25 over the function text contains it 89 times. The note is `paper/writeup.md`.

The command ranks functions with BM25 over the path, signature, docstring and body, then packs whole spans until the budget is spent. A span that does not fit is skipped. The evaluation also reads files from the top, packs functions only inside the top one, three or five files, and scores a symbol graph (name, quoted string, raised exception, test-to-callee) that stays quiet when a signal is common. The graph does not beat the function text. It is built with the standard library parser.

## Run it on a checkout

```bash
python -m editslice /path/to/repo --issue issue.txt --budget 1024
python -m editslice /path/to/repo --issue issue.txt --budget 1024 --json
```

## Reproduce the numbers

The evaluation is the public test split of SWE-bench Lite, 300 instances from 12 Python repositories. Reference patches are used only to name the functions the fix edited. The ranker sees the issue text and the tree at `base_commit`.

```bash
# clones land in data/repos/<name>, about 1.7GB, no working-tree checkout
python experiments/run_eval.py --instances data/swebench_lite.jsonl --repos data/repos
```

`data/swebench_lite.jsonl` is that split with the fields this eval uses (`instance_id`, `repo`, `base_commit`, `problem_statement`, `patch`). It is derived from `princeton-nlp/SWE-bench_Lite` and is not a new labeling of the issues. The derived part is the function-level gold and the per-channel scores in `results/`.

Tokens are `len(text) // 4` for every method, so the budget comparison does not depend on a tokenizer. The graph channels also record a fanout of 4, 8 and 16.

## Layout

`editslice/rank.py` ranks. `pack.py` spends the budget. `graph.py` is the parser. `gold.py` reads a unified diff. `experiments/run_eval.py` writes `results/summary.json`, `results/per_task.jsonl` and `results/table.txt`. The note is `paper/writeup.md`.
