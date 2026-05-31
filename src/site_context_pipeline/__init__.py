"""site-context-pipeline — structured site context for LLM-assisted workflows.

Public surface: see ``cli.main`` for the entrypoint and the artifact builders
in ``inventory``, ``link_graph``, and ``context_pack``. The 0.1 core is
standard-library only; network adapters live behind future opt-in extras.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("site-context-pipeline")
except PackageNotFoundError:  # pragma: no cover - source tree without install
    # Running from a source checkout that was never installed. Keep this in
    # sync with [project].version in pyproject.toml as a last-resort fallback.
    __version__ = "0.4.0"

__all__ = ["__version__"]
