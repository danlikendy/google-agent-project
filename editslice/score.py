"""Ranking and budget metrics. Pure functions, no repository access."""

from __future__ import annotations

from editslice.anchors import GENERIC_NAMES, extract
from editslice.graph import Symbol

BUDGETS = (512, 1024, 2048, 4096)
AT_K = (1, 5, 10)


def mentions_gold_name(issue: str, symbols: list[Symbol]) -> bool:
    """True when the issue literally names a gold function.

    Generic verbs (`get`, `run`, `update`) do not count. An issue that says
    "the update fails" has not pointed at a function named `update`.
    """
    idents = extract(issue).ident_set()
    for symbol in symbols:
        lowered = symbol.name.lower()
        if len(symbol.name) < 5 or symbol.name.startswith("__"):
            continue
        if lowered in GENERIC_NAMES:
            continue
        if lowered in idents:
            return True
    return False


def rank_hit(ranked: list[str], gold: list[str], ks: tuple[int, ...] = AT_K) -> dict[str, bool]:
    wanted = set(gold)
    return {str(k): bool(wanted & set(ranked[:k])) for k in ks}


def reciprocal_rank(ranked: list[str], gold: list[str]) -> float:
    wanted = set(gold)
    for index, sid in enumerate(ranked, start=1):
        if sid in wanted:
            return 1.0 / index
    return 0.0


def budget_hit(packed: list[str], gold: list[str]) -> bool:
    return bool(set(gold) & set(packed))


def budget_recall(packed: list[str], gold: list[str]) -> float:
    if not gold:
        return 0.0
    return len(set(gold) & set(packed)) / len(set(gold))
