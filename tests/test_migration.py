import importlib.util
from pathlib import Path


def test_migrations_structure():
    """Verify all Alembic migration files are valid and export required variables."""
    versions_dir = Path("alembic") / "versions"
    migration_files = sorted(
        [f for f in versions_dir.glob("*.py") if not f.name.startswith("__")],
        key=lambda p: p.name,
    )
    assert len(migration_files) >= 7, "Expected at least 7 migrations in alembic/versions"

    for migration_file in migration_files:
        spec = importlib.util.spec_from_file_location("migration_module", migration_file)
        assert spec is not None and spec.loader is not None

        migration_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration_module)

        assert hasattr(migration_module, "revision")
        assert hasattr(migration_module, "upgrade")
        assert callable(migration_module.upgrade)
        assert hasattr(migration_module, "downgrade")
        assert callable(migration_module.downgrade)
