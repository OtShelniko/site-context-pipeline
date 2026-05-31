# Cite this project

If you use `site-context-pipeline` in academic work, a public
case-study, a vendor comparison, or any other report where
attribution matters, please cite it.

## Quick citation

> site-context-pipeline contributors. *site-context-pipeline*: an
> offline-first CLI for building structured site context packs for
> human-reviewed, LLM-assisted content workflows. MIT License.
> Available at <https://github.com/OtShelniko/site-context-pipeline>.

## Machine-readable metadata

The repository ships a [`CITATION.cff`](https://citation-file-format.github.io/)
file at the repo root. GitHub renders a "Cite this repository" button
on the project page that pulls metadata from that file.

To consume it programmatically:

```bash
# Install the helper.
pip install cffconvert

# Render to BibTeX:
cffconvert -i CITATION.cff -f bibtex

# Render to APA:
cffconvert -i CITATION.cff -f apalike
```

`cffconvert` supports BibTeX, APA, EndNote, RIS, Codemeta,
Zenodo-JSON, and plain-text formats. Pick whichever your workflow
expects.

## Versioning notes

If you cite a specific feature, please also include the version of the
package you used. Every published release has a tag of the form
`v0.X.Y` and is preserved on PyPI:

```bash
pip install site-context-pipeline==0.3.0
```

Version-pinning makes a citation reproducible — readers can install
the exact tooling that produced your results.
