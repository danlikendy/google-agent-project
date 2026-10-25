"""A symbol graph built with the stdlib parser.

Nodes are functions, methods and classes. Edges are the calls we can resolve
without running the program: same file, self, an imported name, a unique
global name, or a name re-exported from a package.
"""

from __future__ import annotations

import ast
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".tox",
        ".venv",
        "venv",
        "env",
        "site-packages",
        "node_modules",
        "build",
        "dist",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".eggs",
    }
)

# Calls to these names are not navigational. Linking them adds edges that
# point nowhere useful and, when the name is unique by accident, point wrong.
_CALL_SKIP = frozenset(
    """
    print len isinstance super range str int list dict set tuple bool float
    type getattr setattr hasattr enumerate zip map filter sorted reversed any
    all min max sum open repr id hash iter next format staticmethod classmethod
    property abs round divmod ord chr hex bin oct vars dir callable issubclass
    object Exception ValueError TypeError KeyError RuntimeError AttributeError
    NotImplementedError OSError ImportError IndexError StopIteration NameError
    assertRaises pytest mock MagicMock patch
    """.split()
)


def skip_path(path: str) -> bool:
    for part in path.split("/"):
        if part in SKIP_DIRS or part.endswith(".egg-info"):
            return True
    return False


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if name in {"test.py", "tests.py", "conftest.py"}:
        return True
    for part in parts[:-1]:
        if part in {"tests", "test", "testing"} or part.startswith("test_"):
            return True
    return False


@dataclass
class Symbol:
    sid: str
    name: str
    qualname: str
    kind: str
    file: str
    start: int
    end: int
    owner: str
    signature: str
    doc: str
    literals: tuple[str, ...]
    raises: tuple[str, ...]
    text: str
    is_test: bool


@dataclass
class Graph:
    symbols: dict[str, Symbol]
    calls: dict[str, tuple[str, ...]]
    files: dict[str, str]

    def candidates(self) -> list[Symbol]:
        """Functions and methods the agent might actually edit."""
        found = [
            symbol
            for symbol in self.symbols.values()
            if symbol.kind in {"function", "method"} and not symbol.is_test
        ]
        found.sort(key=lambda symbol: symbol.sid)
        return found

    def by_file(self, path: str) -> list[Symbol]:
        found = [symbol for symbol in self.symbols.values() if symbol.file == path]
        found.sort(key=lambda symbol: (symbol.start, symbol.end, symbol.sid))
        return found


@dataclass
class _Raw:
    symbol: Symbol
    calls: list[tuple[str, str | None]] = field(default_factory=list)


def _header(lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1) - 1
    picked: list[str] = []
    for index in range(start, min(len(lines), start + 8)):
        picked.append(lines[index].strip())
        if picked[-1].endswith(":"):
            break
    return " ".join(picked)[:240]


def _text(lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", None) or start
    return "\n".join(lines[start - 1 : end])[:12000]


def _walk_body(node: ast.AST):
    """Yield nodes inside `node`, but not nodes inside a nested def or class."""
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for child in ast.iter_child_nodes(node):
        if isinstance(child, nested):
            continue
        yield child
        yield from _walk_body(child)


def _collect_body(node: ast.AST) -> tuple[list[str], list[str], list[tuple[str, str | None]]]:
    literals: list[str] = []
    raises: list[str] = []
    calls: list[tuple[str, str | None]] = []
    seen_lit: set[str] = set()
    seen_raise: set[str] = set()
    for child in _walk_body(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            snippet = " ".join(child.value.split())
            key = snippet.casefold()
            if 4 <= len(snippet) <= 160 and key not in seen_lit and len(literals) < 40:
                seen_lit.add(key)
                literals.append(snippet)
        elif isinstance(child, ast.Raise) and child.exc is not None:
            exc = child.exc.func if isinstance(child.exc, ast.Call) else child.exc
            name = None
            if isinstance(exc, ast.Name):
                name = exc.id
            elif isinstance(exc, ast.Attribute):
                name = exc.attr
            if name and name not in seen_raise:
                seen_raise.add(name)
                raises.append(name)
        elif isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name) and func.id not in _CALL_SKIP:
                calls.append((func.id, None))
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.attr not in _CALL_SKIP:
                    calls.append((func.attr, func.value.id))
    return literals, raises, calls


def _module_files(files: dict[str, str], module: str) -> list[str]:
    if not module:
        return []
    suffix = module.replace(".", "/")
    hits = [
        path
        for path in files
        if path.endswith(suffix + ".py") or path.endswith(suffix + "/__init__.py")
    ]
    hits.sort()
    return hits


class _Builder(ast.NodeVisitor):
    def __init__(self, rel: str, lines: list[str]):
        self.rel = rel
        self.lines = lines
        self.stack: list[tuple[str, str]] = []
        self.raws: list[_Raw] = []
        self.imports: dict[str, tuple[str, str]] = {}
        self.modules: dict[str, str] = {}
        self._ids: set[str] = set()

    def _qualname(self, name: str) -> str:
        if not self.stack:
            return name
        return ".".join(part for _, part in self.stack) + "." + name

    def _owner(self) -> str:
        for kind, _name in reversed(self.stack):
            if kind == "class":
                return ".".join(part for k, part in self.stack if k == "class")
        return ""

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            # `import pkg.mod` binds the top package, which we do not chase.
            if "." not in alias.name:
                self.modules[local] = alias.name
        # Still walk nothing else.

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        dots = node.level or 0
        parts = self.rel.split("/")[:-1]
        if dots:
            keep = parts[: len(parts) - (dots - 1)] if dots else parts
            if node.module:
                keep.extend(node.module.split("."))
            module = ".".join(part for part in keep if part)
        else:
            module = node.module or ""
        for alias in node.names:
            if alias.name == "*":
                continue
            local = alias.asname or alias.name
            self.imports[local] = (module, alias.name)

    def _add(self, node: ast.AST, kind: str) -> None:
        name = getattr(node, "name")
        qualname = self._qualname(name)
        sid = f"{self.rel}:{qualname}"
        if sid in self._ids:
            sid = f"{sid}#{getattr(node, 'lineno', 0)}"
        self._ids.add(sid)
        literals, raises, calls = _collect_body(node)
        doc = ast.get_docstring(node) or ""
        is_test = is_test_path(self.rel) or name.startswith("test_")
        symbol = Symbol(
            sid=sid,
            name=name,
            qualname=qualname,
            kind=kind,
            file=self.rel,
            start=getattr(node, "lineno", 1),
            end=getattr(node, "end_lineno", None) or getattr(node, "lineno", 1),
            owner=self._owner() if kind == "method" else "",
            signature=_header(self.lines, node),
            doc=doc[:600],
            literals=tuple(literals),
            raises=tuple(raises),
            text=_text(self.lines, node),
            is_test=is_test,
        )
        self.raws.append(_Raw(symbol, calls))

    def _absorb_imports(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            if isinstance(child, ast.Import):
                self.visit_Import(child)
            elif isinstance(child, ast.ImportFrom):
                self.visit_ImportFrom(child)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        kind = "method" if any(k == "class" for k, _ in self.stack) else "function"
        self._absorb_imports(node)
        self._add(node, kind)
        self.stack.append(("def", node.name))
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.visit(child)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add(node, "class")
        self.stack.append(("class", node.name))
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.visit(child)
        self.stack.pop()


def _resolve_imported(
    files: dict[str, str],
    file_symbols: dict[str, list[Symbol]],
    records: dict[str, dict[str, tuple[str, str]]],
    module: str,
    name: str,
    depth: int = 0,
) -> str | None:
    if depth > 4 or not module:
        return None
    hits: list[str] = []
    for path in _module_files(files, module):
        for symbol in file_symbols.get(path, []):
            if symbol.name != name:
                continue
            if symbol.kind == "class" or (symbol.kind == "function" and symbol.owner == ""):
                hits.append(symbol.sid)
    unique = list(dict.fromkeys(hits))
    if len(unique) == 1:
        return unique[0]
    if len(unique) > 1:
        return None
    for path in _module_files(files, module):
        record = records.get(path, {}).get(name)
        if record:
            found = _resolve_imported(files, file_symbols, records, record[0], record[1], depth + 1)
            if found:
                return found
    return None


def _build_calls(
    files: dict[str, str],
    raws: list[_Raw],
    records: dict[str, dict[str, tuple[str, str]]],
    modules: dict[str, dict[str, str]],
) -> dict[str, tuple[str, ...]]:
    symbols = {raw.symbol.sid: raw.symbol for raw in raws}
    file_symbols: dict[str, list[Symbol]] = defaultdict(list)
    by_name: dict[str, list[str]] = defaultdict(list)
    methods: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    classes_by_name: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in symbols.values():
        file_symbols[symbol.file].append(symbol)
        if symbol.kind == "class":
            classes_by_name[symbol.name].append(symbol)
        elif symbol.kind in {"function", "method"}:
            by_name[symbol.name].append(symbol.sid)
            if symbol.kind == "method":
                methods[(symbol.file, symbol.owner, symbol.name)].append(symbol.sid)

    import_sid: dict[tuple[str, str], str] = {}
    for path, mapping in records.items():
        for local, (module, original) in mapping.items():
            found = _resolve_imported(files, file_symbols, records, module, original)
            if found:
                import_sid[(path, local)] = found

    def resolve(symbol: Symbol, name: str, base: str | None) -> str | None:
        if base is None:
            imported = import_sid.get((symbol.file, name))
            if imported:
                return imported
            local = [
                item.sid
                for item in file_symbols.get(symbol.file, [])
                if item.name == name and item.kind == "function" and item.owner == ""
            ]
            if len(local) == 1:
                return local[0]
            global_hits = by_name.get(name, [])
            if len(global_hits) == 1:
                return global_hits[0]
            return None
        if base in {"self", "cls"} and symbol.owner:
            found = methods.get((symbol.file, symbol.owner, name), [])
            return found[0] if len(found) == 1 else None
        imported = import_sid.get((symbol.file, base))
        if imported:
            target = symbols.get(imported)
            if target and target.kind == "class":
                found = methods.get((target.file, target.qualname, name), [])
                if len(found) == 1:
                    return found[0]
        module_name = modules.get(symbol.file, {}).get(base)
        if module_name:
            found = _resolve_imported(files, file_symbols, records, module_name, name)
            if found:
                return found
        classes = classes_by_name.get(base, [])
        if len(classes) == 1:
            target = classes[0]
            found = methods.get((target.file, target.qualname, name), [])
            if len(found) == 1:
                return found[0]
        return None

    calls: dict[str, tuple[str, ...]] = {}
    for raw in raws:
        resolved: list[str] = []
        seen: set[str] = set()
        for name, base in raw.calls:
            sid = resolve(raw.symbol, name, base)
            if sid and sid != raw.symbol.sid and sid not in seen and sid in symbols:
                seen.add(sid)
                resolved.append(sid)
        resolved.sort()
        calls[raw.symbol.sid] = tuple(resolved)
    return calls


def build_graph(files: dict[str, str]) -> Graph:
    raws: list[_Raw] = []
    records: dict[str, dict[str, tuple[str, str]]] = {}
    modules: dict[str, dict[str, str]] = {}
    kept = {path: text for path, text in files.items() if path.endswith(".py") and not skip_path(path)}
    for path in sorted(kept):
        text = kept[path]
        if len(text) > 500_000:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(text)
        except SyntaxError:
            continue
        lines = text.splitlines()
        builder = _Builder(path, lines)
        builder.visit(tree)
        raws.extend(builder.raws)
        records[path] = builder.imports
        modules[path] = builder.modules
    symbols = {raw.symbol.sid: raw.symbol for raw in raws}
    calls = _build_calls(kept, raws, records, modules)
    return Graph(symbols=symbols, calls=calls, files=kept)


def build_graph_from_tree(root: Path) -> Graph:
    files: dict[str, str] = {}
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if skip_path(rel):
            continue
        try:
            files[rel] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return build_graph(files)


def covering_function(graph: Graph, path: str, line: int) -> Symbol | None:
    found = [
        symbol
        for symbol in graph.symbols.values()
        if symbol.file == path
        and symbol.kind in {"function", "method"}
        and symbol.start <= line <= symbol.end
    ]
    if not found:
        return None
    found.sort(key=lambda symbol: (symbol.end - symbol.start, symbol.start, symbol.sid))
    return found[0]
