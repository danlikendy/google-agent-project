"""Score EditSlice against SWE-bench Lite.

Reference patches are used only to name the functions the fix edited.
The ranker sees the issue text and the repository at the base commit.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from editslice.anchors import extract  # noqa: E402
from editslice.gitio import files_at_commit  # noqa: E402
from editslice.gold import changed_lines, gold_functions  # noqa: E402
from editslice.graph import build_graph, is_test_path  # noqa: E402
from editslice.pack import pack_files, pack_functions  # noqa: E402
from editslice.rank import (  # noqa: E402
    rank_bm25_files,
    rank_bm25_functions,
    rank_bridge,
    rank_literal,
    rank_name,
    rank_raise,
    rrf,
)
from editslice.score import (  # noqa: E402
    BUDGETS,
    budget_hit,
    budget_recall,
    mentions_gold_name,
    rank_hit,
    reciprocal_rank,
)

CHANNEL_METHODS = ("name", "literal", "raise", "bridge", "editslice", "bm25_func", "bm25_file")


def load_instances(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    return json.loads(raw)


def has_commit(repo: Path, commit: str) -> bool:
    probe = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{commit}^{{commit}}"],
        capture_output=True,
    )
    return probe.returncode == 0


def _pack_ids(graph, ranked: list[str], budget: int, files: bool) -> list[str]:
    if files:
        return [symbol.sid for symbol in pack_files(graph, ranked, budget)]
    return [symbol.sid for symbol in pack_functions(graph, ranked, budget)]


def _cell(ranked: list[str], gold: list[str], packed: dict[int, list[str]]) -> dict:
    return {
        "nonempty": bool(ranked),
        "hit": rank_hit(ranked, gold),
        "mrr": reciprocal_rank(ranked, gold),
        "budget_hit": {str(budget): budget_hit(packed[budget], gold) for budget in BUDGETS},
        "budget_recall": {str(budget): round(budget_recall(packed[budget], gold), 4) for budget in BUDGETS},
    }


def score_graph(graph, issue: str, gold: list[str], fanouts: list[int]) -> dict:
    anchors = extract(issue)
    function_rank = rank_bm25_functions(graph, issue)
    file_rank = rank_bm25_files(graph, issue)
    gold_files = list(dict.fromkeys(graph.symbols[sid].file for sid in gold))
    by_fanout = {}
    for fanout in fanouts:
        channels = {
            "name": rank_name(graph, anchors, fanout),
            "literal": rank_literal(graph, anchors, fanout),
            "raise": rank_raise(graph, anchors, fanout),
            "bridge": rank_bridge(graph, anchors, fanout),
        }
        channels["editslice"] = rrf(
            [channels["name"], channels["literal"], channels["raise"], channels["bridge"]]
        )
        channels["bm25_func"] = function_rank
        block = {}
        for method in ("name", "literal", "raise", "bridge", "editslice", "bm25_func"):
            packed = {budget: _pack_ids(graph, channels[method], budget, False) for budget in BUDGETS}
            block[method] = _cell(channels[method], gold, packed)
        file_packed = {budget: _pack_ids(graph, file_rank, budget, True) for budget in BUDGETS}
        file_cell = _cell(file_rank, gold_files, {budget: [] for budget in BUDGETS})
        # Rank metrics compare files. Budget metrics compare functions inside the prefix.
        file_cell["budget_hit"] = {
            str(budget): budget_hit(file_packed[budget], gold) for budget in BUDGETS
        }
        file_cell["budget_recall"] = {
            str(budget): round(budget_recall(file_packed[budget], gold), 4) for budget in BUDGETS
        }
        block["bm25_file"] = file_cell
        by_fanout[str(fanout)] = block
    return by_fanout


def aggregate(rows: list[dict], fanout: str) -> dict:
    splits = {
        "all": rows,
        "hidden": [row for row in rows if not row["name_visible"]],
        "visible": [row for row in rows if row["name_visible"]],
    }
    table: dict = {}
    for split, items in splits.items():
        table[split] = {"n": len(items), "methods": {}}
        for method in CHANNEL_METHODS:
            hit_counts = {"1": 0, "5": 0, "10": 0}
            budget_counts = {str(budget): 0 for budget in BUDGETS}
            recall_sums = {str(budget): 0.0 for budget in BUDGETS}
            mrr = 0.0
            nonempty = 0
            nonempty_hit10 = 0
            for row in items:
                cell = row["scores"][fanout][method]
                nonempty += int(cell["nonempty"])
                nonempty_hit10 += int(cell["nonempty"] and cell["hit"]["10"])
                for k, flag in cell["hit"].items():
                    hit_counts[k] += int(flag)
                mrr += cell["mrr"]
                for budget, flag in cell["budget_hit"].items():
                    budget_counts[budget] += int(flag)
                for budget, value in cell["budget_recall"].items():
                    recall_sums[budget] += value
            n = len(items)
            denom = n or 1
            vote = nonempty or 1
            table[split]["methods"][method] = {
                "n": n,
                "nonempty": nonempty,
                "hit": {k: hit_counts[k] / denom for k in hit_counts},
                "hit_count": hit_counts,
                "mrr": mrr / denom,
                "budget_hit": {b: budget_counts[b] / denom for b in budget_counts},
                "budget_hit_count": budget_counts,
                "budget_recall": {b: recall_sums[b] / denom for b in recall_sums},
                "hit10_when_voting": nonempty_hit10 / vote,
            }
    return table


def repo_table(rows: list[dict], fanout: str) -> dict:
    by_repo: dict[str, list[dict]] = {}
    for row in rows:
        by_repo.setdefault(row["repo"], []).append(row)
    out = {}
    for repo, items in sorted(by_repo.items()):
        hidden = [row for row in items if not row["name_visible"]]
        out[repo] = {
            "n": len(items),
            "n_hidden": len(hidden),
            "editslice_hit10": _rate(items, fanout, "editslice", "hit", "10"),
            "bm25_func_hit10": _rate(items, fanout, "bm25_func", "hit", "10"),
            "bm25_file_budget1024": _rate(items, fanout, "bm25_file", "budget_hit", "1024"),
            "editslice_budget1024": _rate(items, fanout, "editslice", "budget_hit", "1024"),
            "bm25_func_budget1024": _rate(items, fanout, "bm25_func", "budget_hit", "1024"),
            "hidden_editslice_hit10": _rate(hidden, fanout, "editslice", "hit", "10"),
            "hidden_bm25_func_hit10": _rate(hidden, fanout, "bm25_func", "hit", "10"),
        }
    return out


def _rate(items: list[dict], fanout: str, method: str, field: str, key: str) -> float | None:
    if not items:
        return None
    hits = sum(int(row["scores"][fanout][method][field][key]) for row in items)
    return hits / len(items)


def examples_from(rows: list[dict], instances: dict[str, dict]) -> list[dict]:
    """Hidden issues where the name channel misses and EditSlice still hits."""
    found = []
    for row in rows:
        if row["name_visible"]:
            continue
        cell = row["scores"]["8"]
        if not cell["editslice"]["hit"]["5"] or cell["name"]["hit"]["10"]:
            continue
        issue = instances[row["instance_id"]]["problem_statement"].strip().replace("\n", " ")
        found.append(
            {
                "instance_id": row["instance_id"],
                "repo": row["repo"],
                "gold": row["gold"],
                "issue": issue[:320],
                "editslice_hit10": cell["editslice"]["hit"]["10"],
                "literal_hit10": cell["literal"]["hit"]["10"],
                "raise_hit10": cell["raise"]["hit"]["10"],
                "bridge_hit10": cell["bridge"]["hit"]["10"],
                "bm25_func_hit10": cell["bm25_func"]["hit"]["10"],
                "budget1024": cell["editslice"]["budget_hit"]["1024"],
            }
        )
    return found[:8]


def format_table(summary: dict) -> str:
    lines = [
        "split     method        n   hit@1  hit@5 hit@10    mrr  @1024  @4096  rec@1024  votes",
    ]
    for split, block in summary.items():
        for method, cell in block["methods"].items():
            lines.append(
                f"{split:8}  {method:12} {cell['n']:3}  "
                f"{cell['hit']['1']:6.3f} {cell['hit']['5']:6.3f} {cell['hit']['10']:6.3f}  "
                f"{cell['mrr']:5.3f} {cell['budget_hit']['1024']:6.3f} {cell['budget_hit']['4096']:6.3f}  "
                f"{cell['budget_recall']['1024']:8.3f}  {cell['nonempty']:3}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate EditSlice on SWE-bench Lite.")
    parser.add_argument("--instances", type=Path, default=ROOT / "data" / "swebench_lite.json")
    parser.add_argument("--repos", type=Path, default=ROOT / "data" / "repos")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--repo", action="append", default=[])
    parser.add_argument("--fanout", default="4,8,16")
    args = parser.parse_args(argv)

    fanouts = [int(item) for item in args.fanout.split(",") if item]
    instances = load_instances(args.instances)
    if args.repo:
        wanted = set(args.repo)
        instances = [row for row in instances if row["repo"] in wanted]
    if args.limit:
        instances = instances[: args.limit]
    by_id = {row["instance_id"]: row for row in instances}

    args.out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    skipped: Counter = Counter()
    started = time.time()

    for index, task in enumerate(instances, start=1):
        repo = args.repos / task["repo"].split("/")[-1]
        stamp = time.time()
        if not repo.exists():
            skipped["missing_repo"] += 1
            print(f"[{index}/{len(instances)}] skip {task['instance_id']}: no clone", flush=True)
            continue
        if not has_commit(repo, task["base_commit"]):
            skipped["missing_commit"] += 1
            print(f"[{index}/{len(instances)}] skip {task['instance_id']}: commit not in clone", flush=True)
            continue
        try:
            files = files_at_commit(repo, task["base_commit"])
            graph = build_graph(files)
            gold = gold_functions(graph, task["patch"])
        except Exception:
            skipped["error"] += 1
            traceback.print_exc()
            continue
        if not gold:
            touched = changed_lines(task["patch"])
            production = {path: lines for path, lines in touched.items() if not is_test_path(path)}
            reason = "outside_function" if production else "no_production_diff"
            skipped[reason] += 1
            print(f"[{index}/{len(instances)}] skip {task['instance_id']}: {reason}", flush=True)
            continue
        gold_symbols = [graph.symbols[sid] for sid in gold]
        visible = mentions_gold_name(task["problem_statement"], gold_symbols)
        try:
            scores = score_graph(graph, task["problem_statement"], gold, fanouts)
        except Exception:
            skipped["error"] += 1
            traceback.print_exc()
            continue
        row = {
            "instance_id": task["instance_id"],
            "repo": task["repo"],
            "name_visible": visible,
            "n_gold": len(gold),
            "gold": [graph.symbols[sid].qualname for sid in gold],
            "gold_files": sorted({graph.symbols[sid].file for sid in gold}),
            "scores": scores,
        }
        rows.append(row)
        cell = scores["8"] if "8" in scores else scores[str(fanouts[0])]
        flag = "Y" if cell["editslice"]["hit"]["10"] else "n"
        print(
            f"[{index}/{len(instances)}] {task['instance_id']}  "
            f"{time.time() - stamp:.1f}s  gold={len(gold)}  "
            f"{'visible' if visible else 'hidden'}  slice@10={flag}",
            flush=True,
        )
        if index % 25 == 0:
            _write(args.out, rows, skipped, fanouts, partial=True)

    summary = {str(fanout): aggregate(rows, str(fanout)) for fanout in fanouts}
    payload = {
        "benchmark": "SWE-bench Lite test",
        "source": "princeton-nlp/SWE-bench_Lite",
        "n_instances": len(instances),
        "n_scored": len(rows),
        "skipped": dict(skipped),
        "fanouts": fanouts,
        "budgets": list(BUDGETS),
        "seconds": round(time.time() - started, 1),
        "summary": summary,
        "by_repo": repo_table(rows, "8") if 8 in fanouts else {},
        "examples": examples_from(rows, by_id) if 8 in fanouts else [],
    }
    _write(args.out, rows, skipped, fanouts, partial=False, payload=payload)
    if "8" in payload["summary"]:
        print("\n" + format_table(payload["summary"]["8"]))
    print(f"\nscored {len(rows)}  skipped {dict(skipped)}  {payload['seconds']}s")
    return 0


def _write(out: Path, rows: list[dict], skipped: Counter, fanouts: list[int], partial: bool, payload: dict | None = None) -> None:
    per_task = out / ("per_task.partial.jsonl" if partial else "per_task.jsonl")
    with per_task.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    if payload is not None:
        (out / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        (out / "table.txt").write_text(format_table(payload["summary"]["8"]) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
