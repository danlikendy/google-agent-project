"""Rank functions an agent should open.

Each channel abstains when its signal points at too many functions. A quote
that occurs in half the repository, or an exception raised from dozens of
places, is not a localization signal, and letting it vote drowns the channels
that are actually specific. The surviving lists are fused with reciprocal
rank fusion, which has no learned weights.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from editslice.anchors import GENERIC_NAMES, Anchors, extract, tokenize
from editslice.graph import Graph, Symbol

RRF_K = 60
# A signal that hits more functions than this is treated as boilerplate.
DEFAULT_FANOUT = 8
_MAX_HITS = 20


def _candidates(graph: Graph) -> list[Symbol]:
    return graph.candidates()


def _name_df(graph: Graph) -> Counter:
    counts: Counter = Counter()
    for symbol in _candidates(graph):
        counts.update(set(tokenize(symbol.name)))
    return counts


def _sorted(scores: dict[str, float]) -> list[str]:
    return sorted(scores, key=lambda sid: (-scores[sid], sid))


def rank_name(graph: Graph, anchors: Anchors, fanout: int = DEFAULT_FANOUT) -> list[str]:
    idents = anchors.ident_set()
    tokens = anchors.token_set()
    df = _name_df(graph)
    name_count = Counter(symbol.name.lower() for symbol in _candidates(graph))
    scores: dict[str, float] = {}
    exact: dict[str, bool] = {}
    for symbol in _candidates(graph):
        score = 0.0
        is_exact = False
        lname = symbol.name.lower()
        if (
            len(symbol.name) >= 5
            and not symbol.name.startswith("__")
            and lname not in GENERIC_NAMES
            and lname in idents
            and name_count[lname] <= fanout
        ):
            score += 10
            is_exact = True
        for token in set(tokenize(symbol.name)):
            if len(token) >= 5 and token in tokens and df[token] <= fanout:
                score += 1
        if score:
            scores[symbol.sid] = score
            exact[symbol.sid] = is_exact
    if len(scores) > _MAX_HITS:
        scores = {sid: value for sid, value in scores.items() if exact.get(sid)}
    if not scores or len(scores) > _MAX_HITS:
        return []
    return _sorted(scores)


def _literal_match(quote: str, constants: list[str]) -> bool:
    for const in constants:
        if quote == const:
            return True
        short, long = (quote, const) if len(quote) <= len(const) else (const, quote)
        if len(short) >= 12 and short in long:
            return True
    return False


def rank_literal(graph: Graph, anchors: Anchors, fanout: int = DEFAULT_FANOUT) -> list[str]:
    quotes = []
    seen: set[str] = set()
    for literal in anchors.literals:
        key = literal.casefold()
        if len(key) >= 8 and key not in seen:
            seen.add(key)
            quotes.append(key)
    if not quotes:
        return []
    prepared = [
        (symbol.sid, [item.casefold() for item in symbol.literals])
        for symbol in _candidates(graph)
        if symbol.literals
    ]
    scores: dict[str, float] = {}
    for quote in quotes:
        hits = [sid for sid, constants in prepared if _literal_match(quote, constants)]
        if not hits or len(hits) > fanout:
            continue
        for sid in hits:
            scores[sid] = scores.get(sid, 0.0) + 1
    if not scores or len(scores) > _MAX_HITS:
        return []
    return _sorted(scores)


def _exception_names(anchors: Anchors) -> set[str]:
    """Exception names from the issue.

    Names ending in Error are the obvious ones. Projects also invent names
    like PortInUse, which are just CamelCase and would be missed by a suffix
    list. Everyday capitalized words get into this set too; they only matter
    if some function actually raises them, and the fanout rule drops them
    when that happens all over the repository.
    """
    wanted = {name.lower() for name in anchors.exceptions}
    for name in anchors.identifiers:
        if (
            len(name) >= 6
            and name[0].isupper()
            and any(char.islower() for char in name)
            and "_" not in name
        ):
            wanted.add(name.lower())
    return wanted


def rank_raise(graph: Graph, anchors: Anchors, fanout: int = DEFAULT_FANOUT) -> list[str]:
    wanted = _exception_names(anchors)
    if not wanted:
        return []
    by_exc: dict[str, list[str]] = defaultdict(list)
    for symbol in _candidates(graph):
        for name in symbol.raises:
            key = name.lower()
            if key in wanted:
                by_exc[key].append(symbol.sid)
    scores: dict[str, float] = {}
    for sids in by_exc.values():
        unique = list(dict.fromkeys(sids))
        if not unique or len(unique) > fanout:
            continue
        for sid in unique:
            scores[sid] = scores.get(sid, 0.0) + 1
    if not scores or len(scores) > _MAX_HITS:
        return []
    return _sorted(scores)


def rank_bridge(graph: Graph, anchors: Anchors, fanout: int = DEFAULT_FANOUT) -> list[str]:
    """Tests whose names share a rare token with the issue, then their callees."""
    tests = [
        symbol
        for symbol in graph.symbols.values()
        if symbol.is_test and symbol.kind in {"function", "method"}
    ]
    if not tests:
        return []
    df: Counter = Counter()
    named: dict[str, set[str]] = {}
    for symbol in tests:
        tokens = set(tokenize(symbol.name))
        named[symbol.sid] = tokens
        df.update(tokens)
    issue_tokens = anchors.token_set()
    seeds: list[tuple[int, str]] = []
    for symbol in tests:
        shared = [
            token
            for token in named[symbol.sid] & issue_tokens
            if len(token) >= 5 and df[token] <= fanout
        ]
        if shared:
            seeds.append((len(shared), symbol.sid))
    seeds.sort(key=lambda item: (-item[0], item[1]))
    seeds = seeds[:fanout]
    if not seeds:
        return []

    def production_callees(sid: str, hops: int) -> dict[str, float]:
        scores: dict[str, float] = {}
        frontier = [sid]
        seen = {sid}
        for hop in range(hops):
            nxt: list[str] = []
            weight = 1.0 if hop == 0 else 0.5
            for current in frontier:
                for callee in graph.calls.get(current, ()):
                    if callee in seen:
                        continue
                    seen.add(callee)
                    symbol = graph.symbols.get(callee)
                    if symbol is None:
                        continue
                    if symbol.is_test or symbol.kind not in {"function", "method"}:
                        nxt.append(callee)
                        continue
                    scores[callee] = scores.get(callee, 0.0) + weight
                    nxt.append(callee)
            frontier = nxt
        return scores

    hop1: dict[str, float] = {}
    for weight, sid in seeds:
        for callee, value in production_callees(sid, 1).items():
            hop1[callee] = hop1.get(callee, 0.0) + weight * value
    if len(hop1) > _MAX_HITS:
        return []
    if hop1:
        # The function the test calls is often a wrapper. Take its callees
        # too, but only while the whole set still fits on one short list.
        union = dict(hop1)
        for sid, value in hop1.items():
            for callee in graph.calls.get(sid, ()):
                symbol = graph.symbols.get(callee)
                if symbol is None or symbol.is_test or symbol.kind not in {"function", "method"}:
                    continue
                if callee not in union:
                    union[callee] = value * 0.5
        if len(union) <= _MAX_HITS:
            return _sorted(union)
        return _sorted(hop1)
    hop2: dict[str, float] = {}
    for weight, sid in seeds:
        for callee, value in production_callees(sid, 2).items():
            hop2[callee] = hop2.get(callee, 0.0) + weight * value
    if 0 < len(hop2) <= _MAX_HITS:
        return _sorted(hop2)
    return []


def rrf(rankings: list[list[str]], k: int = RRF_K) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for index, sid in enumerate(ranking):
            scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + index + 1)
    if not scores:
        return []
    return _sorted(scores)


def bm25_top(
    docs: list[tuple[str, list[str]]],
    query: list[str],
    topn: int = 100,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[str]:
    if not docs or not query:
        return []
    inverted: dict[str, list[tuple[int, int]]] = defaultdict(list)
    lengths: list[int] = []
    for index, (_sid, tokens) in enumerate(docs):
        counts = Counter(tokens)
        lengths.append(len(tokens) or 1)
        for token, count in counts.items():
            inverted[token].append((index, count))
    average = sum(lengths) / len(docs)
    scores = [0.0] * len(docs)
    for token in dict.fromkeys(query):
        postings = inverted.get(token)
        if not postings:
            continue
        df = len(postings)
        idf = math.log(1.0 + (len(docs) - df + 0.5) / (df + 0.5))
        for index, count in postings:
            denom = count + k1 * (1 - b + b * lengths[index] / average)
            scores[index] += idf * (count * (k1 + 1)) / denom
    order = sorted(range(len(docs)), key=lambda index: (-scores[index], docs[index][0]))
    return [docs[index][0] for index in order[:topn] if scores[index] > 0]


def rank_bm25_functions(graph: Graph, issue: str, topn: int = 100) -> list[str]:
    docs = []
    for symbol in _candidates(graph):
        blob = f"{symbol.file} {symbol.qualname} {symbol.signature} {symbol.doc} {symbol.text}"
        docs.append((symbol.sid, tokenize(blob)[:1500]))
    return bm25_top(docs, tokenize(issue), topn=topn)


def keep_in_files(graph: Graph, function_ids: list[str], files: list[str]) -> list[str]:
    """Function ranking restricted to a file shortlist, order preserved."""
    allowed = set(files)
    return [sid for sid in function_ids if graph.symbols[sid].file in allowed]


def rank_bm25_files(graph: Graph, issue: str, topn: int = 30) -> list[str]:
    from editslice.graph import is_test_path

    docs = []
    for path in sorted(graph.files):
        if is_test_path(path):
            continue
        docs.append((path, tokenize(graph.files[path])[:4000]))
    return bm25_top(docs, tokenize(issue), topn=topn)


@dataclass(frozen=True)
class Analysis:
    channels: dict[str, list[str]]
    fused: list[str]
    files: list[str]
    support: dict[str, tuple[str, ...]]


def analyze(graph: Graph, issue: str, fanout: int = DEFAULT_FANOUT) -> Analysis:
    anchors = extract(issue)
    channels = {
        "name": rank_name(graph, anchors, fanout),
        "literal": rank_literal(graph, anchors, fanout),
        "raise": rank_raise(graph, anchors, fanout),
        "bridge": rank_bridge(graph, anchors, fanout),
    }
    fused = rrf([channels["name"], channels["literal"], channels["raise"], channels["bridge"]])
    if not fused:
        fused = rank_bm25_functions(graph, issue, topn=20)
        channels["fallback_bm25"] = fused
    support: dict[str, list[str]] = defaultdict(list)
    for name, ranking in channels.items():
        for sid in ranking[:10]:
            support[sid].append(name)
    return Analysis(
        channels=channels,
        fused=fused,
        files=rank_bm25_files(graph, issue),
        support={sid: tuple(names) for sid, names in support.items()},
    )
