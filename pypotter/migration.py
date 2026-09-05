"""Safe helpers for moving legacy PyPotter state into the web release."""

import shutil
from datetime import UTC, datetime
from pathlib import Path


def backup_database(database_path: Path) -> Path | None:
    if not database_path.exists():
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = database_path.with_name(
        f"{database_path.stem}.backup-{stamp}{database_path.suffix}"
    )
    shutil.copy2(database_path, destination)
    return destination


def legacy_training_files(training_dir: Path) -> list[Path]:
    """Return legacy training files without mutating or deleting the corpus."""
    if not training_dir.exists():
        return []
    return sorted(path for path in training_dir.rglob("*") if path.is_file())
