"""Pack whole function spans into a token budget.

The unit is the function, not the file. A function that does not fit is
skipped, and a span already covered by a selected neighbor is not charged
twice. Tokens are estimated as one per four characters, which is close enough
for code and is the same estimate for every method we compare.
"""

from __future__ import annotations

from editslice.graph import Graph, Symbol, is_test_path


def token_cost(text: str) -> int:
    return max(1, len(text) // 4)


def pack_functions(graph: Graph, ranked: list[str], budget: int) -> list[Symbol]:
    chosen: list[Symbol] = []
    used = 0
    for sid in ranked:
        symbol = graph.symbols.get(sid)
        if symbol is None or symbol.is_test or symbol.kind not in {"function", "method"}:
            continue
        if any(_overlaps(symbol, earlier) for earlier in chosen):
            continue
        cost = token_cost(symbol.text)
        if used + cost > budget:
            continue
        chosen.append(symbol)
        used += cost
    return chosen


def pack_files(graph: Graph, ranked_files: list[str], budget: int) -> list[Symbol]:
    """Functions whose entire span sits in the prefix of a selected file.

    This is the baseline an agent gets from opening BM25's top files at the
    top and reading until the budget runs out.
    """
    covered: list[Symbol] = []
    seen: set[str] = set()
    remaining = budget
    for path in ranked_files:
        if remaining <= 0:
            break
        if is_test_path(path):
            continue
        text = graph.files.get(path, "")
        if not text:
            continue
        take = min(len(text), remaining * 4)
        prefix_lines = text[:take].count("\n") + 1
        for symbol in graph.by_file(path):
            if symbol.kind not in {"function", "method"} or symbol.is_test:
                continue
            if symbol.end <= prefix_lines and symbol.sid not in seen:
                seen.add(symbol.sid)
                covered.append(symbol)
        remaining -= token_cost(text[:take])
    return covered


def _overlaps(left: Symbol, right: Symbol) -> bool:
    if left.file != right.file:
        return False
    return not (left.end < right.start or right.end < left.start)
