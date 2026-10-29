"""Ask Gemma whether a packed context contains the edited function.

Two reads of the same 1024-token budget are compared. `prefix` is the top of
the files BM25 ranks. `spans` is whole functions from BM25 over function text.
`infile` keeps those functions only when they live in the top-ranked file.
The model replies with one name. A hit is that name matching a gold function.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from editslice.gitio import files_at_commit  # noqa: E402
from editslice.gold import gold_functions  # noqa: E402
from editslice.graph import build_graph, is_test_path  # noqa: E402
from editslice.pack import pack_functions, token_cost  # noqa: E402
from editslice.rank import keep_in_files, rank_bm25_files, rank_bm25_functions  # noqa: E402

REPOS = ROOT / "data" / "repos"
HOST = "http://127.0.0.1:11435"
IDENT = __import__("re").compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def prefix_text(graph, ranked_files: list[str], budget: int) -> str:
    parts: list[str] = []
    remaining = budget
    for path in ranked_files:
        if remaining <= 0 or is_test_path(path):
            continue
        text = graph.files.get(path, "")
        if not text:
            continue
        chunk = text[: min(len(text), remaining * 4)]
        parts.append(f"# {path}\n{chunk}")
        remaining -= token_cost(chunk)
    return "\n\n".join(parts)


def span_text(graph, ranked_ids: list[str], budget: int) -> str:
    parts = [f"# {symbol.file}\n{symbol.text}" for symbol in pack_functions(graph, ranked_ids, budget)]
    return "\n\n".join(parts)


def ask(model: str, issue: str, code: str) -> str:
    prompt = (
        "You are locating the function a bug report asks to change.\n"
        "Reply with the function name only.\n\n"
        f"Bug report:\n{issue[:4000]}\n\n"
        f"Code:\n{code}\n\n"
        "Function name:"
    )
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": 24, "num_ctx": 4096},
        }
    ).encode()
    request = urllib.request.Request(
        HOST + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        payload = json.loads(response.read().decode())
    return payload.get("response", "").strip()


def predicted(answer: str) -> str:
    found = IDENT.findall(answer)
    return found[-1] if found else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask Gemma to name the function inside a packed context.")
    parser.add_argument("--model", default="gemma4:12b-it-qat")
    parser.add_argument("--budget", type=int, default=1024)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "model_asks.jsonl")
    args = parser.parse_args(argv)

    suites = [
        ("gemma4", ROOT / "data" / "gemma4_tasks.jsonl"),
        ("swebench", ROOT / "data" / "swebench_lite.jsonl"),
    ]
    done = {(row["instance_id"], row["mode"]) for row in load_jsonl(args.out)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    handle = args.out.open("a", encoding="utf-8")
    for suite, path in suites:
        tasks = load_jsonl(path)
        if args.limit:
            tasks = tasks[: args.limit]
        for index, task in enumerate(tasks, start=1):
            modes_left = [mode for mode in ("prefix", "spans", "infile") if (task["instance_id"], mode) not in done]
            if not modes_left:
                continue
            repo = REPOS / task["repo"].split("/")[-1]
            stamp = time.time()
            try:
                files = files_at_commit(repo, task["base_commit"])
                graph = build_graph(files)
                gold = gold_functions(graph, task["patch"])
            except Exception as exc:  # noqa: BLE001
                print(f"[{suite} {index}] {task['instance_id']} skip {exc}", flush=True)
                continue
            if not gold:
                print(f"[{suite} {index}] {task['instance_id']} skip no gold", flush=True)
                continue
            symbols = [graph.symbols[sid] for sid in gold]
            names = {symbol.name.lower() for symbol in symbols}
            file_rank = rank_bm25_files(graph, task["problem_statement"])
            function_rank = rank_bm25_functions(graph, task["problem_statement"], topn=200)
            top_file = file_rank[0] if file_rank else ""
            contexts = {
                "prefix": prefix_text(graph, file_rank, args.budget),
                "spans": span_text(graph, function_rank, args.budget),
                "infile": span_text(graph, keep_in_files(graph, function_rank, file_rank[:1]), args.budget),
            }
            for mode in modes_left:
                started = time.time()
                answer = ask(args.model, task["problem_statement"], contexts[mode])
                guess = predicted(answer)
                row = {
                    "suite": suite,
                    "instance_id": task["instance_id"],
                    "repo": task["repo"],
                    "mode": mode,
                    "model": args.model,
                    "budget": args.budget,
                    "file_hit1": any(symbol.file == top_file for symbol in symbols),
                    "gold": sorted(names),
                    "guess": guess,
                    "hit": guess.lower() in names,
                    "answer": answer,
                    "seconds": round(time.time() - started, 2),
                }
                handle.write(json.dumps(row) + "\n")
                handle.flush()
                print(
                    f"[{suite} {index}/{len(tasks)}] {task['instance_id']} {mode} "
                    f"{'Y' if row['hit'] else 'n'} {row['seconds']:.1f}s",
                    flush=True,
                )
            print(f"    built {time.time() - stamp:.1f}s", flush=True)
    handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
