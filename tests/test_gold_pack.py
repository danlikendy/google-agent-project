import tempfile
import unittest
from pathlib import Path

from editslice.gold import changed_lines, gold_functions
from editslice.graph import Symbol, build_graph_from_tree
from editslice.pack import pack_functions, token_cost
from tests.test_graph import write_repo

DIFF = """\
diff --git a/pkg/server.py b/pkg/server.py
--- a/pkg/server.py
+++ b/pkg/server.py
@@ -6,1 +6,1 @@ class Server:
-        if port < 1024:
+        if port < 1:
         raise PortInUse("port already bound")
"""

TEST_ONLY = """\
--- a/tests/test_server.py
+++ b/tests/test_server.py
@@ -3,1 +3,1 @@
-def test_binding_privileged_port():
+def test_binding_privileged_port():
"""


def _symbol(sid: str, text: str, start: int, end: int, file: str = "a.py") -> Symbol:
    name = sid.split(":")[-1]
    return Symbol(
        sid=sid,
        name=name,
        qualname=name,
        kind="function",
        file=file,
        start=start,
        end=end,
        owner="",
        signature=f"def {name}():",
        doc="",
        literals=(),
        raises=(),
        text=text,
        is_test=False,
    )


class GoldPackTests(unittest.TestCase):
    def test_gold_is_the_function_around_the_deleted_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_repo(root)
            graph = build_graph_from_tree(root)
        self.assertEqual(changed_lines(DIFF), {"pkg/server.py": {6}})
        gold = gold_functions(graph, DIFF)
        self.assertEqual([graph.symbols[sid].name for sid in gold], ["open_socket"])
        self.assertEqual(gold_functions(graph, TEST_ONLY), [])

    def test_pack_skips_a_span_that_does_not_fit(self):
        big = _symbol("a.py:big", "x" * 400, 1, 20)
        small = _symbol("a.py:small", "x" * 40, 30, 40)
        graph_symbols = {big.sid: big, small.sid: small}

        class _Graph:
            symbols = graph_symbols

        packed = pack_functions(_Graph(), [big.sid, small.sid], budget=token_cost(small.text))
        self.assertEqual([item.name for item in packed], ["small"])

    def test_overlap_is_not_packed_twice(self):
        outer = _symbol("a.py:outer", "x" * 80, 1, 40)
        inner = _symbol("a.py:inner", "x" * 40, 10, 20)

        class _Graph:
            symbols = {outer.sid: outer, inner.sid: inner}

        packed = pack_functions(_Graph(), [outer.sid, inner.sid], budget=1000)
        self.assertEqual([item.name for item in packed], ["outer"])


if __name__ == "__main__":
    unittest.main()
