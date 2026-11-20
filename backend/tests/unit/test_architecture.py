"""Dependency direction (API -> services -> domain; inner layers never import outer ones) and
source hygiene."""

import ast
import unicodedata
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"

FORBIDDEN_IMPORTS = {
    "domain": ("fastapi", "starlette", "sqlalchemy", "app.api", "app.services", "app.infrastructure"),
    "services": ("fastapi", "starlette", "app.api"),
    "core": ("fastapi", "starlette", "sqlalchemy", "app.api", "app.services", "app.infrastructure"),
}


def imported_modules(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


@pytest.mark.parametrize("layer", sorted(FORBIDDEN_IMPORTS))
def test_layer_does_not_import_outer_layers_or_frameworks(layer):
    files = sorted((APP_DIR / layer).rglob("*.py"))
    assert files, f"no source files found for layer {layer}"

    violations = [
        f"{path.relative_to(APP_DIR)} imports {module}"
        for path in files
        for module in imported_modules(path)
        if module.startswith(FORBIDDEN_IMPORTS[layer])
    ]

    assert violations == []


def test_python_sources_contain_no_invisible_characters():
    # Bidi controls and other invisible format characters (Unicode "Cf") can make code read
    # differently from how it runs ("Trojan Source"); write them as \u escapes instead.
    backend = APP_DIR.parent
    files = [p for folder in ("app", "tests", "migrations") for p in (backend / folder).rglob("*.py")]

    found = [
        f"{path.relative_to(backend)}:{number}: U+{ord(char):04X}"
        for path in files
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for char in line
        if unicodedata.category(char) == "Cf"
    ]

    assert files
    assert found == []
