"""Allow ``python -m site_context_pipeline ...`` as an alias for the CLI."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
