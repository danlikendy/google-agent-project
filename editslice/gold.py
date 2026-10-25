"""Gold edit loci from a unified diff.

A function is gold when a deleted line of the fix falls inside it. Pure
insertions, which have no deleted line, are attributed to the function that
contains the line they are inserted before. Test files are ignored: the
benchmark asks where the production code changed, and the new tests are not
available to the agent anyway.
"""

from __future__ import annotations

import re

from editslice.graph import Graph, covering_function, is_test_path

_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")


def changed_lines(diff: str) -> dict[str, set[int]]:
    """Map a base-version path to the old line numbers the fix touches."""
    deletions: dict[str, set[int]] = {}
    insertions: dict[str, set[int]] = {}
    path: str | None = None
    old_line = 0
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("--- "):
            in_hunk = False
            old = line[4:].strip().split("\t", 1)[0]
            if old.startswith("a/"):
                old = old[2:]
            path = None if old == "/dev/null" or not old.endswith(".py") else old
            continue
        match = _HUNK.match(line)
        if match and path:
            in_hunk = True
            old_line = int(match.group(1))
            continue
        if not in_hunk or path is None:
            continue
        if line.startswith("@@") or line.startswith("diff --git "):
            in_hunk = False
            continue
        if line.startswith("\\"):
            continue
        if line.startswith("+"):
            insertions.setdefault(path, set()).add(max(old_line, 1))
            continue
        if line.startswith("-"):
            deletions.setdefault(path, set()).add(old_line)
            old_line += 1
            continue
        if line.startswith(" "):
            old_line += 1
            continue
        in_hunk = False

    chosen: dict[str, set[int]] = {}
    for item in set(deletions) | set(insertions):
        if deletions.get(item):
            chosen[item] = set(deletions[item])
        else:
            chosen[item] = set(insertions.get(item, set()))
    return chosen


def gold_functions(graph: Graph, diff: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for path, lines in changed_lines(diff).items():
        if is_test_path(path):
            continue
        for line in sorted(lines):
            symbol = covering_function(graph, path, line)
            if symbol is None or symbol.is_test or symbol.sid in seen:
                continue
            seen.add(symbol.sid)
            found.append(symbol.sid)
    return found
