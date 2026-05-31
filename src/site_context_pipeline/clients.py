"""Client workspace layout and small filesystem helpers.

A *client* is an isolated workspace (directory tree) that holds one site's
inputs, intermediate data, and generated artifacts. The default workspace
root is the current working directory; users can point elsewhere with the
``--workspace`` flag on the CLI.

Layout (created by ``init_client``)::

    <workspace>/clients/<client>/
        input/
            urls.csv              # user-provided
            links.csv             # user-provided (optional)
            project.md            # editorial notes (optional)
        config/
        data/                     # generated: content_inventory.json, ...
        output/                   # generated: agent_context_pack.{md,json}, ...
        logs/

The layout intentionally mirrors public examples like
``examples/demo-client/`` so the same commands work in either place.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Conservative client-id pattern; rejects path traversal and shell metachars.
_CLIENT_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


@dataclass(frozen=True)
class ClientPaths:
    """Resolved filesystem layout for one client workspace."""

    workspace_root: Path
    client_code: str
    root: Path
    input: Path
    config: Path
    data: Path
    output: Path
    logs: Path

    @property
    def all_directories(self) -> list[Path]:
        return [self.root, self.input, self.config, self.data, self.output, self.logs]


def validate_client_code(client_code: str) -> str:
    """Reject unsafe client identifiers before they touch the filesystem."""
    if not isinstance(client_code, str) or not _CLIENT_ID_RE.match(client_code):
        raise ValueError(
            f"invalid client code: {client_code!r}; "
            "use letters, digits, dot, underscore, or hyphen (max 64 chars)"
        )
    return client_code


def resolve_workspace_root(workspace: str | Path | None) -> Path:
    """Pick a workspace root.

    When the caller passes a path, we use it. Otherwise we use the current
    working directory. Either way the path is resolved to an absolute one so
    later code can compare paths reliably.
    """
    if workspace is None:
        return Path.cwd().resolve()
    return Path(workspace).resolve()


def get_client_paths(client_code: str, workspace: str | Path | None = None) -> ClientPaths:
    validate_client_code(client_code)
    root_workspace = resolve_workspace_root(workspace)
    root = root_workspace / "clients" / client_code
    return ClientPaths(
        workspace_root=root_workspace,
        client_code=client_code,
        root=root,
        input=root / "input",
        config=root / "config",
        data=root / "data",
        output=root / "output",
        logs=root / "logs",
    )


def init_client(paths: ClientPaths, *, write: bool) -> dict[str, Any]:
    """Plan (or perform) creation of an empty client workspace.

    Returns a dict shaped like the standard CLI payload: ``planned_writes``
    always present, ``written_files`` populated only when ``write`` is true.
    """
    planned = [str(directory) for directory in paths.all_directories]
    placeholder_targets = [
        paths.input / "project.md",
        paths.input / "urls.csv",
        paths.input / "links.csv",
    ]
    planned.extend(str(p) for p in placeholder_targets)

    result: dict[str, Any] = {
        "planned_writes": planned,
        "warnings": [],
        "written_files": [],
        "skipped_existing": [],
    }
    if not write:
        return result

    for directory in paths.all_directories:
        directory.mkdir(parents=True, exist_ok=True)
        result["written_files"].append(str(directory))

    if not (paths.input / "project.md").exists():
        (paths.input / "project.md").write_text(
            _project_md_template(paths.client_code), encoding="utf-8"
        )
        result["written_files"].append(str(paths.input / "project.md"))
    else:
        result["skipped_existing"].append(str(paths.input / "project.md"))

    if not (paths.input / "urls.csv").exists():
        (paths.input / "urls.csv").write_text(_urls_csv_template(), encoding="utf-8")
        result["written_files"].append(str(paths.input / "urls.csv"))
    else:
        result["skipped_existing"].append(str(paths.input / "urls.csv"))

    if not (paths.input / "links.csv").exists():
        (paths.input / "links.csv").write_text(_links_csv_template(), encoding="utf-8")
        result["written_files"].append(str(paths.input / "links.csv"))
    else:
        result["skipped_existing"].append(str(paths.input / "links.csv"))

    return result


def read_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _project_md_template(client: str) -> str:
    return (
        f"# Project notes — {client}\n"
        "\n"
        "Optional free-form editorial notes about the site. The pipeline does\n"
        "not interpret this file in 0.1; it is included verbatim in the\n"
        "agent context pack so a human reviewer can read it alongside the\n"
        "generated artifacts.\n"
    )


def _urls_csv_template() -> str:
    return (
        "url,title,h1,status_code,word_count,inlinks_count,outlinks_count\n"
    )


def _links_csv_template() -> str:
    return "source_url,target_url,anchor_text\n"
