"""Local-file importers that turn third-party formats into the row shapes
the toolkit's builders accept.

Each importer is a thin, stdlib-only adapter:

* it reads a local file path;
* it returns plain dicts in the shape ``inventory.build_inventory`` /
  ``link_graph.build_link_graph`` expect;
* it never makes a network call;
* it raises a typed error on malformed input.

0.2 ships the sitemap XML importer and the Screaming Frog CSV importer.
"""

from .screaming_frog import (
    ScreamingFrogImportError,
)
from .screaming_frog import (
    detect_flavour as detect_screaming_frog_flavour,
)
from .screaming_frog import (
    read_inventory_csv as read_screaming_frog_inventory,
)
from .screaming_frog import (
    read_link_csv as read_screaming_frog_links,
)
from .sitemap_xml import SitemapImportError, read_sitemap

__all__ = [
    "ScreamingFrogImportError",
    "SitemapImportError",
    "detect_screaming_frog_flavour",
    "read_screaming_frog_inventory",
    "read_screaming_frog_links",
    "read_sitemap",
]
