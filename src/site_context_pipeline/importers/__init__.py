"""Local-file importers that turn third-party formats into the row shapes
the toolkit's builders accept.

Each importer is a thin, stdlib-only adapter:

* it reads a local file path;
* it returns plain dicts in the shape ``inventory.build_inventory`` /
  ``link_graph.build_link_graph`` expect;
* it never makes a network call;
* it raises a typed error on malformed input.

0.2 ships the sitemap XML importer; the Screaming Frog CSV importer follows.
"""

from .sitemap_xml import SitemapImportError, read_sitemap

__all__ = ["SitemapImportError", "read_sitemap"]
