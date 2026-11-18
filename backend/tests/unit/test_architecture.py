"""Dependency direction: API -> services -> domain. Inner layers must not import outer ones."""

import ast
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
