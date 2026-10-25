import tempfile
import unittest
from pathlib import Path

from editslice.anchors import extract
from editslice.graph import build_graph, build_graph_from_tree
from editslice.rank import rank_bridge, rank_literal, rank_name, rank_raise, rrf
from editslice.score import mentions_gold_name
from tests.test_graph import write_repo

ISSUE = (
    'Binding a privileged port fails with "port already bound". '
    "PortInUse is raised and the process stops.\n"
)


class RankTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write_repo(self.root)
        self.graph = build_graph_from_tree(self.root)
        self.target = next(s.sid for s in self.graph.symbols.values() if s.name == "open_socket")

    def tearDown(self):
        self.tmp.cleanup()

    def test_channels_find_the_function_the_issue_does_not_name(self):
        self.assertNotIn("open_socket", ISSUE)
        self.assertFalse(
            mentions_gold_name(ISSUE, [self.graph.symbols[self.target]])
        )
        anchors = extract(ISSUE)
        self.assertEqual(rank_literal(self.graph, anchors), [self.target])
        self.assertEqual(rank_raise(self.graph, anchors), [self.target])
        self.assertEqual(rank_bridge(self.graph, anchors), [self.target])
        self.assertNotIn(self.target, rank_name(self.graph, anchors))
        self.assertEqual(
            rrf(
                [
                    rank_name(self.graph, anchors),
                    rank_literal(self.graph, anchors),
                    rank_raise(self.graph, anchors),
                    rank_bridge(self.graph, anchors),
                ]
            )[0],
            self.target,
        )

    def test_raise_abstains_when_the_exception_is_everywhere(self):
        files = {
            f"pkg/m{i}.py": f"def place_{i}():\n    raise BoomError('nope')\n" for i in range(9)
        }
        graph = build_graph(files)
        anchors = extract("BoomError showed up in production.")
        self.assertEqual(rank_raise(graph, anchors, fanout=8), [])

    def test_literal_abstains_on_a_boilerplate_string(self):
        files = {
            f"pkg/m{i}.py": f"def place_{i}():\n    note = 'connection reset by peer'\n" for i in range(9)
        }
        graph = build_graph(files)
        anchors = extract('The log says "connection reset by peer" over and over.')
        self.assertEqual(rank_literal(graph, anchors, fanout=8), [])


if __name__ == "__main__":
    unittest.main()
