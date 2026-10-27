"""Pack the functions an issue points at into a token budget."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from editslice.gitio import files_at_commit
from editslice.graph import build_graph, build_graph_from_tree
from editslice.pack import pack_functions, token_cost
from editslice.rank import rank_bm25_functions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pack the functions an issue points at into a token budget.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--issue", required=True, type=Path)
    parser.add_argument("--commit", help="read this commit instead of the working tree")
    parser.add_argument("--budget", type=int, default=1024)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    issue = args.issue.read_text(encoding="utf-8", errors="replace")
    if args.commit:
        graph = build_graph(files_at_commit(args.repo, args.commit))
    else:
        graph = build_graph_from_tree(args.repo)
    if not graph.symbols:
        print(
            "no Python files found. The clones in data/repos have no checkout; pass --commit.",
            file=sys.stderr,
        )
        return 1
    ranked = rank_bm25_functions(graph, issue, topn=200)
    packed = pack_functions(graph, ranked, args.budget)
    spans = [
        {
            "symbol": symbol.qualname,
            "file": symbol.file,
            "start": symbol.start,
            "end": symbol.end,
            "tokens": token_cost(symbol.text),
        }
        for symbol in packed
    ]
    used = sum(item["tokens"] for item in spans)
    if args.as_json:
        print(json.dumps({"budget_tokens": args.budget, "tokens_used": used, "spans": spans}, indent=2))
        return 0
    print(f"budget {args.budget}  used {used}")
    for index, item in enumerate(spans, start=1):
        print(f"{index:2}. {item['file']}:{item['start']}-{item['end']}  {item['symbol']}  {item['tokens']} tok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
