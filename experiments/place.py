"""Where the edited function sits inside the file BM25 ranks first.

Also records how many other functions share a gold name. The ranker is not
changed. This only measures the tasks already scored.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from editslice.anchors import GENERIC_NAMES, extract  # noqa: E402
from editslice.gitio import files_at_commit  # noqa: E402
from editslice.gold import gold_functions  # noqa: E402
from editslice.graph import build_graph  # noqa: E402
from editslice.pack import token_cost  # noqa: E402
from editslice.rank import rank_bm25_files  # noqa: E402

REPOS = ROOT / "data" / "repos"


def _prefix(text: str, line: int) -> str:
    if line <= 1:
        return ""
    cut = 0
    seen = 1
    for index, char in enumerate(text):
        if char == "\n":
            seen += 1
            if seen == line:
                cut = index + 1
                break
    return text[:cut]


def measure(task: dict) -> dict | None:
    repo = REPOS / task["repo"].split("/")[-1]
    files = files_at_commit(repo, task["base_commit"])
    graph = build_graph(files)
    gold = gold_functions(graph, task["patch"])
    if not gold:
        return None
    symbols = [graph.symbols[sid] for sid in gold]
    ranking = rank_bm25_files(graph, task["problem_statement"])
    top = ranking[0] if ranking else ""
    in_top = [symbol for symbol in symbols if symbol.file == top]
    before = through = span = None
    if in_top:
        earliest = min(in_top, key=lambda symbol: symbol.end)
        text = graph.files.get(top, "")
        before = token_cost(_prefix(text, earliest.start)) if text else 0
        through = token_cost(_prefix(text, earliest.end + 1)) if text else 0
        span = token_cost(earliest.text)
    counts = Counter(symbol.name.lower() for symbol in graph.candidates())
    idents = extract(task["problem_statement"]).ident_set()
    named = []
    for symbol in symbols:
        lowered = symbol.name.lower()
        if len(symbol.name) < 5 or symbol.name.startswith("__") or lowered in GENERIC_NAMES:
            continue
        if lowered in idents:
            named.append(counts[lowered])
    return {
        "instance_id": task["instance_id"],
        "repo": task["repo"],
        "file_hit1": bool(in_top),
        "tokens_before": before,
        "tokens_through": through,
        "span_tokens": span,
        "name_counts": named,
    }


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def summarize(rows: list[dict]) -> dict:
    hits = [row for row in rows if row["file_hit1"]]
    before = [row["tokens_before"] for row in hits]
    through = [row["tokens_through"] for row in hits]
    named = [row for row in rows if row["name_counts"]]
    unique = [row for row in named if min(row["name_counts"]) == 1]
    collided = [row for row in named if min(row["name_counts"]) > 1]
    return {
        "n": len(rows),
        "file_hit1": len(hits),
        "before_median": _median(before),
        "through_median": _median(through),
        "before_over_1024": sum(value > 1024 for value in before),
        "through_over_1024": sum(value > 1024 for value in through),
        "named": len(named),
        "unique_name": len(unique),
        "colliding_name": len(collided),
        "unique_count_median": _median([min(row["name_counts"]) for row in unique]) if unique else None,
        "collision_median": _median([min(row["name_counts"]) for row in collided]) if collided else None,
    }


def main() -> int:
    suites = [
        ("gemma4", ROOT / "data" / "gemma4_tasks.jsonl"),
        ("swebench", ROOT / "data" / "swebench_lite.jsonl"),
    ]
    out = {}
    for name, path in suites:
        rows = []
        tasks = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        started = time.time()
        for index, task in enumerate(tasks, start=1):
            repo = REPOS / task["repo"].split("/")[-1]
            if not repo.exists():
                continue
            try:
                row = measure(task)
            except Exception as exc:  # noqa: BLE001
                print(f"[{name} {index}] {task['instance_id']} error {exc}", flush=True)
                continue
            if row is None:
                continue
            rows.append(row)
            if index % 10 == 0:
                print(f"[{name} {index}/{len(tasks)}] {time.time() - started:.0f}s", flush=True)
        out[name] = {"summary": summarize(rows), "rows": rows}
        print(name, json.dumps(out[name]["summary"]), flush=True)
        dest = ROOT / "results" / "place.json"
        dest.write_text(json.dumps(out), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
