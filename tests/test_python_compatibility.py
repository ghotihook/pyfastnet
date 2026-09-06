"""The shipped package must actually run on the Python it advertises.

pyproject.toml declares `requires-python = ">=3.7"`. That is a promise to
anyone on an older interpreter — a Raspberry Pi on Bullseye ships 3.9 — and
it is easy to break accidentally, because development happens on a current
Python where newer syntax just works.

These tests check the promise mechanically instead of trusting it: the
shipped modules must parse under the oldest supported grammar, must not use
syntax that needs a later version, and must import only stdlib modules that
existed then. They deliberately cover only `fastnet_decoder/` — tests and
tools are developer-side and may use anything.

If you intentionally raise the floor, change MIN_PYTHON here and
`requires-python` together.
"""

import ast
import pathlib

import pytest

MIN_PYTHON = (3, 7)

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "fastnet_decoder"
PYPROJECT = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"

SHIPPED = sorted(PACKAGE.rglob("*.py"))

# Modules present in the standard library at MIN_PYTHON. A shipped module
# importing anything outside this set either needs a newer Python or is a new
# runtime dependency — both are decisions, not accidents.
ALLOWED_IMPORTS = {
    "datetime", "json", "logging", "pathlib", "queue",
    "collections", "math", "re", "struct", "sys", "os", "itertools", "typing",
}


def test_there_is_something_to_check():
    assert SHIPPED, "no shipped modules found — has the package moved?"


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.name)
def test_parses_under_the_oldest_supported_grammar(path):
    # feature_version rejects syntax newer than MIN_PYTHON (walrus, match,
    # positional-only params, and so on).
    ast.parse(path.read_text(encoding="utf-8"), feature_version=MIN_PYTHON)


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.name)
def test_no_subscripted_builtin_generics(path):
    # list[int] / dict[str, int] are 3.9+; ast.parse accepts them at any
    # feature_version because they are only invalid at runtime.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = [
        f"line {node.lineno}: {node.value.id}[...]"
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id in {"list", "dict", "set", "tuple", "type", "frozenset"}
    ]
    assert not offenders, (
        f"{path.name} uses builtin generics, which need Python 3.9+:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.name)
def test_imports_only_long_standing_stdlib(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    unexpected = imported - ALLOWED_IMPORTS
    assert not unexpected, (
        f"{path.name} imports {sorted(unexpected)} — if that is a new runtime "
        f"dependency it must go in pyproject.toml's `dependencies`; if it is "
        f"stdlib, confirm it exists on Python {'.'.join(map(str, MIN_PYTHON))} "
        f"and add it to ALLOWED_IMPORTS."
    )


def test_declared_requires_python_matches_what_is_checked():
    declared = PYPROJECT.read_text(encoding="utf-8")
    expected = f'requires-python = ">={".".join(map(str, MIN_PYTHON))}"'
    assert expected in declared, (
        f"pyproject.toml no longer declares {expected!r} — update MIN_PYTHON in "
        f"this file so the checks above test the version actually promised."
    )
