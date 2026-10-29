"""Constrain sanitization output to a configured, local workspace."""
from __future__ import annotations

from pathlib import Path


class OutputWorkspaceError(ValueError):
    """Requested output path is outside or unsafe for the configured workspace."""


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def resolve_output_path(output_path: str | Path, workspace_root: str | Path) -> Path:
    """Resolve a destination inside a workspace; reject traversal and symlinks.

    This validation is defense in depth. It does not by itself defeat a hostile
    concurrent local process swapping directory entries after validation.
    """
    raw = Path(output_path).expanduser()
    workspace = Path(workspace_root).expanduser()
    if not workspace.is_absolute() or not raw.parts or ".." in raw.parts:
        raise OutputWorkspaceError("Ausgabepfad ist ungültig oder enthält Traversierung.")
    try:
        workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise OutputWorkspaceError("Ausgabebereich ist nicht verfügbar.") from exc
    if _has_symlink_component(workspace):
        raise OutputWorkspaceError("Ausgabebereich enthält einen symbolischen Link.")
    root = workspace.resolve(strict=True)
    candidate = raw if raw.is_absolute() else root / raw
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise OutputWorkspaceError("Ausgabepfad liegt außerhalb des konfigurierten Ausgabebereichs.") from exc
    parent = candidate.parent
    if _has_symlink_component(parent):
        raise OutputWorkspaceError("Ausgabepfad enthält einen symbolischen Link.")
    try:
        resolved_parent = parent.resolve(strict=True)
        resolved_parent.relative_to(root)
    except (OSError, ValueError) as exc:
        raise OutputWorkspaceError("Zielordner liegt außerhalb des Ausgabebereichs oder ist nicht verfügbar.") from exc
    if not resolved_parent.is_dir():
        raise OutputWorkspaceError("Zielordner ist kein Verzeichnis.")
    destination = resolved_parent / candidate.name
    if destination.is_symlink() or destination.exists():
        raise FileExistsError("Die Zieldatei existiert bereits oder ist ein symbolischer Link.")
    return destination
