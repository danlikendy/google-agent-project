# EditSlice

Pack the functions a bug report points at, under a token budget. When BM25's first file is the file that changes, the edited function still begins a median of 1727 tokens into it on SWE-bench Lite and 1629 tokens into it on the competition's development tasks. Reading that file from the top contains the edit 21 and 9 times. Packing functions inside the same file contains it 48 and 17 times. Gemma 4 12B QAT, given those same 1024 tokens, names the gold function 109 times from packed spans and 88 times from the file prefix on SWE-bench Lite, and 48 versus 38 on the development set. The note is `paper/writeup.md`.

The command ranks functions with BM25 over the path, signature, docstring and body, then packs whole spans until the budget is spent. A span that does not fit is skipped. The evaluation also reads files from the top, packs functions only inside the top one, three or five files, and scores a symbol graph (name, quoted string, raised exception, test-to-callee) that stays quiet when a signal is common. The graph does not beat the function text. It is built with the standard library parser.

## Run it on a checkout

The clones under `data/repos` have no working tree. Pass the commit.

```bash
python3 -m editslice data/repos/requests --commit 110048f9837f8441ea536804115e80b69f400277 --issue examples/requests-1963.txt
```

## Reproduce the numbers

The evaluation is the public test split of SWE-bench Lite, 300 instances from 12 Python repositories. Reference patches are used only to name the functions the fix edited. The ranker sees the issue text and the tree at `base_commit`.

```bash
# clones land in data/repos/<name>, about 1.7GB, no working-tree checkout
python experiments/run_eval.py --instances data/swebench_lite.jsonl --repos data/repos

# the 129 public development tasks; writes results/gemma4/
python experiments/fetch_devset.py
python experiments/run_eval.py --instances data/gemma4_tasks.jsonl --repos data/repos --out results/gemma4

# Gemma 4 12B QAT names the function inside each packing
python experiments/ask_model.py
```

`data/swebench_lite.jsonl` is that split with the fields this eval uses (`instance_id`, `repo`, `base_commit`, `problem_statement`, `patch`). It is derived from `princeton-nlp/SWE-bench_Lite` and is not a new labeling of the issues. The derived part is the function-level gold and the per-channel scores in `results/`.

Tokens are `len(text) // 4` for every method, so the budget comparison does not depend on a tokenizer. The graph channels also record a fanout of 4, 8 and 16.

## Layout

`editslice/rank.py` ranks. `pack.py` spends the budget. `graph.py` is the parser. `gold.py` reads a unified diff. `experiments/run_eval.py` writes `results/summary.json`, `results/per_task.jsonl` and `results/table.txt`. The note is `paper/writeup.md`.
