"""Argparse-based CLI for site-context-pipeline.

Commands:

* Core (offline, dependency-free):
    init, build-inventory, build-link-graph, build-context-pack, inspect.

* Provider commands (read external data into the workspace):
    import-keywords, import-search-performance, list-providers.

Every command supports ``--write``; without it the command runs in
dry-run mode and prints what *would* be written. Output is always one
JSON document on stdout, so the CLI can be piped to tools that ingest
JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .clients import ClientPaths, get_client_paths, init_client, write_json
from .context_pack import build_context_pack
from .inventory import build_inventory
from .link_graph import build_link_graph
from .providers import (
    ProviderConfigurationError,
    ProviderError,
    available_providers,
    get_keyword_provider,
    get_search_evidence_provider,
    get_search_performance_provider,
)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-providers":
        payload = _run_list_providers()
        sys.stdout.write(_dump_json(payload))
        return 0 if payload.get("ok") else 1

    paths = get_client_paths(args.client, workspace=getattr(args, "workspace", None))

    if args.command == "init":
        payload = _run_init(paths, write=args.write)
    elif args.command == "build-inventory":
        payload = _run_build_inventory(paths, args)
    elif args.command == "build-link-graph":
        payload = _run_build_link_graph(paths, args)
    elif args.command == "build-context-pack":
        payload = _run_build_context_pack(paths, args)
    elif args.command == "inspect":
        payload = _run_inspect(paths)
    elif args.command == "import-keywords":
        payload = _run_import_keywords(paths, args)
    elif args.command == "import-search-performance":
        payload = _run_import_search_performance(paths, args)
    elif args.command == "import-search-evidence":
        payload = _run_import_search_evidence(paths, args)
    else:  # pragma: no cover — argparse guards this
        parser.error(f"unknown command: {args.command}")
        return 2

    sys.stdout.write(_dump_json(payload))
    return 0 if payload.get("ok") else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="site-context-pipeline",
        description=(
            "Convert site crawls and editorial notes into structured context "
            "packs for human-reviewed LLM-assisted content workflows."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    common_client = argparse.ArgumentParser(add_help=False)
    common_client.add_argument("--client", required=True, help="Client workspace identifier")
    common_client.add_argument(
        "--workspace",
        default=None,
        help="Workspace root (defaults to the current directory)",
    )
    common_client.add_argument(
        "--write",
        action="store_true",
        help="Persist artifacts to disk; without this flag the command is a dry-run",
    )

    sub.add_parser("init", parents=[common_client], help="Create an empty client workspace")

    inv = sub.add_parser(
        "build-inventory",
        parents=[common_client],
        help="Build content_inventory.json from a CSV / JSON / sitemap.xml URL list",
    )
    inv.add_argument(
        "--source",
        default=None,
        help=(
            "Path to a CSV, JSON, or sitemap XML URL list "
            "(defaults to <client>/input/urls.csv)"
        ),
    )
    inv.add_argument(
        "--format",
        dest="source_format",
        default="auto",
        choices=["auto", "csv", "json", "sitemap", "screaming-frog"],
        help=(
            "Force a particular reader; default 'auto' picks by file "
            "extension and header sniffing (Screaming Frog inventory CSVs "
            "are auto-detected)."
        ),
    )

    lnk = sub.add_parser(
        "build-link-graph",
        parents=[common_client],
        help="Build internal_link_graph.json from a CSV / JSON / Screaming Frog edge list",
    )
    lnk.add_argument(
        "--source",
        default=None,
        help="Path to a CSV or JSON edge list (defaults to <client>/input/links.csv)",
    )
    lnk.add_argument(
        "--format",
        dest="source_format",
        default="auto",
        choices=["auto", "csv", "json", "screaming-frog"],
        help=(
            "Force a particular reader; default 'auto' picks by file "
            "extension and header sniffing (Screaming Frog all_inlinks.csv "
            "is auto-detected)."
        ),
    )

    sub.add_parser(
        "build-context-pack",
        parents=[common_client],
        help="Aggregate inventory + link graph + project notes into one pack",
    )
    sub.add_parser(
        "inspect",
        parents=[common_client],
        help="Report which expected files are present in the workspace",
    )

    kw = sub.add_parser(
        "import-keywords",
        parents=[common_client],
        help=(
            "Import keyword metrics from a provider into "
            "<client>/data/keyword_metrics.json"
        ),
    )
    kw.add_argument(
        "--provider",
        required=True,
        help="Provider slug (see `list-providers`)",
    )
    kw.add_argument(
        "--source",
        default=None,
        help="Provider-specific input path (e.g. CSV file for local-csv)",
    )
    kw.add_argument(
        "--config",
        default=None,
        help="Provider config (JSON file). Optional, used by future live adapters.",
    )

    sp = sub.add_parser(
        "import-search-performance",
        parents=[common_client],
        help=(
            "Import per-query performance data into "
            "<client>/data/search_performance.json"
        ),
    )
    sp.add_argument(
        "--provider",
        required=True,
        help="Provider slug (see `list-providers`)",
    )
    sp.add_argument(
        "--source",
        default=None,
        help="Provider-specific input path (e.g. CSV file for local-gsc-csv)",
    )
    sp.add_argument(
        "--config",
        default=None,
        help="Provider config (JSON file). Optional, used by future live adapters.",
    )

    se = sub.add_parser(
        "import-search-evidence",
        parents=[common_client],
        help=(
            "Import hand-curated SERP-evidence rows into "
            "<client>/data/search_evidence.json"
        ),
    )
    se.add_argument(
        "--provider",
        required=True,
        help="Provider slug (see `list-providers`)",
    )
    se.add_argument(
        "--source",
        default=None,
        help="Provider-specific input path (e.g. CSV file for local-serp-csv)",
    )
    se.add_argument(
        "--config",
        default=None,
        help="Provider config (JSON file). Optional, reserved for future live adapters.",
    )

    sub.add_parser(
        "list-providers",
        help="List available keyword and search-performance providers",
    )

    return parser


def _run_init(paths: ClientPaths, *, write: bool) -> dict[str, Any]:
    data = init_client(paths, write=write)
    return _result_from_data(paths, "init", write=write, data=data)


def _run_build_inventory(paths: ClientPaths, args: argparse.Namespace) -> dict[str, Any]:
    data = build_inventory(
        paths,
        write=args.write,
        source=args.source,
        source_format=getattr(args, "source_format", None),
    )
    return _result_from_data(paths, "build-inventory", write=args.write, data=data)


def _run_build_link_graph(paths: ClientPaths, args: argparse.Namespace) -> dict[str, Any]:
    data = build_link_graph(
        paths,
        write=args.write,
        source=args.source,
        source_format=getattr(args, "source_format", None),
    )
    return _result_from_data(paths, "build-link-graph", write=args.write, data=data)


def _run_build_context_pack(paths: ClientPaths, args: argparse.Namespace) -> dict[str, Any]:
    data = build_context_pack(paths, write=args.write)
    return _result_from_data(paths, "build-context-pack", write=args.write, data=data)


def _run_inspect(paths: ClientPaths) -> dict[str, Any]:
    expected: list[tuple[str, Path]] = [
        ("workspace_root", paths.workspace_root),
        ("client_root", paths.root),
        ("input_dir", paths.input),
        ("config_dir", paths.config),
        ("data_dir", paths.data),
        ("output_dir", paths.output),
        ("logs_dir", paths.logs),
        ("input/urls.csv", paths.input / "urls.csv"),
        ("input/links.csv", paths.input / "links.csv"),
        ("input/project.md", paths.input / "project.md"),
        ("data/content_inventory.json", paths.data / "content_inventory.json"),
        ("data/internal_link_graph.json", paths.data / "internal_link_graph.json"),
        ("data/keyword_metrics.json", paths.data / "keyword_metrics.json"),
        ("data/search_performance.json", paths.data / "search_performance.json"),
        ("data/search_evidence.json", paths.data / "search_evidence.json"),
        ("output/agent_context_pack.json", paths.output / "agent_context_pack.json"),
        ("output/agent_context_pack.md", paths.output / "agent_context_pack.md"),
        ("output/content_opportunities.md", paths.output / "content_opportunities.md"),
    ]
    checks = [{"name": name, "path": str(path), "ok": path.exists()} for name, path in expected]
    required_names = {"workspace_root", "client_root", "input_dir"}
    missing_required = [item for item in checks if not item["ok"] and item["name"] in required_names]

    payload = _base_payload(paths, "inspect", dry_run=True)
    payload["data"] = {"checks": checks}
    payload["ok"] = not missing_required
    if missing_required:
        payload["errors"] = [f"missing:{item['name']}" for item in missing_required]
    return payload


def _run_list_providers() -> dict[str, Any]:
    return {
        "ok": True,
        "command": "list-providers",
        "data": {"providers": available_providers()},
        "warnings": [],
        "errors": [],
    }


def _run_import_keywords(paths: ClientPaths, args: argparse.Namespace) -> dict[str, Any]:
    return _run_provider(
        paths,
        command="import-keywords",
        provider_name=args.provider,
        source=args.source,
        config_path=args.config,
        write=args.write,
        getter=get_keyword_provider,
        target_path=paths.data / "keyword_metrics.json",
    )


def _run_import_search_performance(
    paths: ClientPaths, args: argparse.Namespace
) -> dict[str, Any]:
    return _run_provider(
        paths,
        command="import-search-performance",
        provider_name=args.provider,
        source=args.source,
        config_path=args.config,
        write=args.write,
        getter=get_search_performance_provider,
        target_path=paths.data / "search_performance.json",
    )


def _run_import_search_evidence(
    paths: ClientPaths, args: argparse.Namespace
) -> dict[str, Any]:
    return _run_provider(
        paths,
        command="import-search-evidence",
        provider_name=args.provider,
        source=args.source,
        config_path=args.config,
        write=args.write,
        getter=get_search_evidence_provider,
        target_path=paths.data / "search_evidence.json",
    )


def _run_provider(
    paths: ClientPaths,
    *,
    command: str,
    provider_name: str,
    source: str | None,
    config_path: str | None,
    write: bool,
    getter: Any,
    target_path: Path,
) -> dict[str, Any]:
    payload = _base_payload(paths, command, dry_run=not write)
    payload["planned_writes"] = [str(target_path)]

    try:
        provider = getter(provider_name)
    except ProviderError as error:
        payload["ok"] = False
        payload["errors"] = [str(error)]
        return payload

    provider_config: dict[str, Any] | None = None
    if config_path:
        try:
            with Path(config_path).open("r", encoding="utf-8") as file:
                provider_config = json.load(file)
        except OSError as error:
            payload["ok"] = False
            payload["errors"] = [f"provider_config_unreadable:{error}"]
            return payload
        except json.JSONDecodeError as error:
            payload["ok"] = False
            payload["errors"] = [f"provider_config_invalid_json:{error}"]
            return payload

    try:
        result = provider.run(source=source, provider_config=provider_config)
    except ProviderError as error:
        payload["ok"] = False
        payload["errors"] = [str(error)]
        return payload

    payload["ok"] = bool(result.ok)
    payload["warnings"] = list(result.warnings)
    payload["errors"] = list(result.errors)

    items = result.items
    payload["data"] = {
        "provider": result.provider,
        "items_count": len(items),
        "metadata": result.metadata,
        "preview": items[:5],
    }

    if write and result.ok and items:
        artifact = {
            "schema_version": 1,
            "provider": result.provider,
            "items_count": len(items),
            "metadata": result.metadata,
            "warnings": list(result.warnings),
            "items": items,
        }
        write_json(target_path, artifact)
        payload["written_files"] = [str(target_path)]
        payload["write_performed"] = True
    elif write and not items:
        payload["warnings"].append("no_items_returned_skipping_write")
    return payload


def _result_from_data(
    paths: ClientPaths,
    command: str,
    *,
    write: bool,
    data: dict[str, Any],
) -> dict[str, Any]:
    payload = _base_payload(paths, command, dry_run=not write)
    payload["planned_writes"] = list(data.get("planned_writes") or [])
    payload["written_files"] = list(data.get("written_files") or [])
    payload["skipped_existing"] = list(data.get("skipped_existing") or [])
    payload["warnings"] = list(data.get("warnings") or [])
    payload["errors"] = list(data.get("errors") or [])
    payload["write_performed"] = bool(write and payload["written_files"])
    payload["data"] = {
        key: value
        for key, value in data.items()
        if key not in {"planned_writes", "written_files", "skipped_existing", "warnings", "errors"}
    }
    if data.get("errors"):
        payload["ok"] = False
    return payload


def _base_payload(paths: ClientPaths, command: str, *, dry_run: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "command": command,
        "client": paths.client_code,
        "dry_run": dry_run,
        "write_performed": False,
        "planned_writes": [],
        "written_files": [],
        "skipped_existing": [],
        "warnings": [],
        "errors": [],
        "data": {},
    }


def _dump_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


# Re-export for tests that need to assert on the error type
__all__ = ["main", "ProviderConfigurationError"]
