# EditSlice

On SWE-bench Lite, ranking the right file is not the same as having the edit in context. File-level BM25 puts a gold file in its top 10 on 155 of 280 function-level tasks, and the first 1024 tokens of the retrieved files contain the edited function only 21 times. Packing function spans from BM25 over the function text contains it 89 times. A test-to-callee walk, a raised exception, and a quoted string were tried as seeds for the cases where the issue never names the function. The test walk votes on 161 of those 203 issues and hits none of them. The note is `paper/writeup.md`.

A local agent still needs the function it is about to edit, in a budget it can actually spend. The packer below builds that list. On this benchmark the list worth packing comes from the function text, not from the call graph.

EditSlice builds a symbol graph from a Python tree, ranks functions with four channels that stay quiet when their signal is common, and packs the surviving spans into a token budget. The channels are the function name, a quoted string from the issue, an exception the function raises, and a test whose name shares a rare token with the issue and whose calls reach production code. A channel votes only when the signal points at eight functions or fewer. The lists that remain are fused with reciprocal rank fusion.

The graph is built with the standard library parser. It does not use the competition's 256-dimensional node embeddings, and it does not need the Kaggle graph dump. Call edges are the ones a static reader can defend: an import, `self`, a class attribute, or a name that exists in exactly one place.

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

Primary fanout is 8. The run also records 4 and 16 so the threshold is visible rather than silent. Tokens are `len(text) // 4` for every method, so the budget comparison does not depend on a tokenizer.

## Layout

`editslice/graph.py` builds the graph. `rank.py` is the channels and the fusion. `pack.py` spends the budget. `gold.py` reads a unified diff. `experiments/run_eval.py` writes `results/summary.json`, `results/per_task.jsonl` and `results/table.txt`. The note for the paper track is `paper/writeup.md`.
