from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def test_migrations_form_one_linear_chain():
    # Reads the migration files only; nothing connects to a database.
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))

    assert [revision.revision for revision in script.walk_revisions()] == ["0002", "0001"]
    assert script.get_heads() == ["0002"]
