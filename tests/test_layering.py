import ast
from pathlib import Path

JEV = Path(__file__).resolve().parent.parent / "hive_trader" / "jev"
FORBIDDEN = {"risk", "policy", "execution", "loop", "app", "ledger"}


def test_layering():
    """The reflex layer must not be able to reach sizing, limits or order placement."""
    for f in JEV.glob("*.py"):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = set(node.module.split("."))
                assert not (parts & FORBIDDEN), f"{f.name} imports {node.module}"
