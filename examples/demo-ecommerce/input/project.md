# Project notes — demo-ecommerce

A second synthetic example for the test suite and documentation. The
fictional retailer "Shop Example" sells coffee equipment (espresso
machines, drip coffee makers, burr grinders) on a fictional
`shop.example.com` domain.

This demo intentionally exercises a different IA than `demo-client`:
deep category trees, individual product pages, a shopping cart and
checkout flow, and a small editorial blog supporting the storefront.
The classifier rules in `config/classifier.json` show how to tell
products apart from categories, and how to demote `cart` / `checkout`
out of the indexable inventory.

These notes are reproduced verbatim in the agent context pack. Keep
this file short and factual.

- Audience: home coffee enthusiasts buying their first or second
  serious espresso setup.
- Tone: practical, gear-aware, no marketing fluff.
- Out of scope: commercial cafe equipment, subscription coffee.
