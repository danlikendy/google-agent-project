"""Show the edit slice for one repository and one issue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from editslice.graph import build_graph_from_tree
from editslice.pack import pack_functions, token_cost
from editslice.rank import DEFAULT_FANOUT, analyze


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pack the functions an issue points at into a token budget."
    )
    parser.add_argument("repo", type=Path, help="checkout of the repository")
    parser.add_argument("--issue", required=True, type=Path, help="text file with the issue")
    parser.add_argument("--budget", type=int, default=1024)
    parser.add_argument("--fanout", type=int, default=DEFAULT_FANOUT)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    issue = args.issue.read_text(encoding="utf-8", errors="replace")
    graph = build_graph_from_tree(args.repo)
    found = analyze(graph, issue, fanout=args.fanout)
    packed = pack_functions(graph, found.fused, args.budget)
    spans = []
    for symbol in packed:
        spans.append(
            {
                "symbol": symbol.qualname,
                "file": symbol.file,
                "start": symbol.start,
                "end": symbol.end,
                "tokens": token_cost(symbol.text),
                "channels": list(found.support.get(symbol.sid, ())),
            }
        )
    payload = {
        "budget_tokens": args.budget,
        "tokens_used": sum(item["tokens"] for item in spans),
        "abstained": "fallback_bm25" in found.channels,
        "spans": spans,
    }
    if args.as_json:
        print(json.dumps(payload, indent=2))
        return 0

    if payload["abstained"]:
        print("No name, quote, exception or test was specific enough. Showing a BM25 fallback.")
    else:
        fired = [name for name, ranking in found.channels.items() if ranking and name != "fallback_bm25"]
        print("channels: " + ", ".join(fired))
    print(f"budget {args.budget}  used {payload['tokens_used']}")
    if not spans:
        print("nothing fit in the budget")
        return 0
    for index, item in enumerate(spans, start=1):
        via = ", ".join(item["channels"]) or "fused"
        print(
            f"{index:2}. {item['file']}:{item['start']}-{item['end']}"
            f"  {item['symbol']}  {item['tokens']} tok  via {via}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
