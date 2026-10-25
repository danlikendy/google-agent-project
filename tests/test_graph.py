import tempfile
import unittest
from pathlib import Path

from editslice.graph import build_graph, build_graph_from_tree

SERVER = """\
class PortInUse(Exception):
    pass


class Server:
    def open_socket(self, port):
        if port < 1024:
            raise PortInUse("port already bound")
        return port

    def status(self):
        return "ok"
"""

TEST = """\
from pkg.server import Server


def test_binding_privileged_port():
    Server.open_socket(80)
"""


def write_repo(root: Path) -> None:
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "server.py").write_text(SERVER)
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_server.py").write_text(TEST)


class GraphTests(unittest.TestCase):
    def test_call_from_test_reaches_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_repo(root)
            graph = build_graph_from_tree(root)
        methods = [s for s in graph.symbols.values() if s.name == "open_socket"]
        self.assertEqual(len(methods), 1)
        method = methods[0]
        self.assertEqual(method.kind, "method")
        self.assertFalse(method.is_test)
        self.assertIn("port already bound", method.literals)
        self.assertIn("PortInUse", method.raises)
        tests = [s for s in graph.symbols.values() if s.name == "test_binding_privileged_port"]
        self.assertEqual(len(tests), 1)
        self.assertIn(method.sid, graph.calls[tests[0].sid])

    def test_same_file_and_import_resolution(self):
        files = {
            "pkg/util.py": "def format_title(text):\n    return text.strip()\n",
            "pkg/app.py": (
                "from pkg.util import format_title\n\n"
                "def render_page(text):\n"
                "    return format_title(text)\n"
            ),
        }
        graph = build_graph(files)
        render = next(s for s in graph.symbols.values() if s.name == "render_page")
        title = next(s for s in graph.symbols.values() if s.name == "format_title")
        self.assertIn(title.sid, graph.calls[render.sid])


if __name__ == "__main__":
    unittest.main()
