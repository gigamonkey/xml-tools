# xml-tools

Two small, generic XML command-line tools, depending only on the Python
standard library plus `lxml`:

- `format_xml.py` → the `xml-format` command: a config-driven XML
  pretty-printer. All format-specific behavior lives in a caller-supplied JSON
  config; the code hardcodes nothing about any particular XML vocabulary.
- `identify.py` → the `xml-identify` command: stamps `uuid` attributes onto
  XPath matches.

## Tech Stack

- Python 3.10+, `lxml`
- Package manager: `uv`; build backend: `hatchling`
- Installable as a `uv tool` (`uv tool install .`), which puts `xml-format` and
  `xml-identify` on `PATH`.

## Layout

- `format_xml.py`, `identify.py` — the two tools (flat top-level modules; entry
  points are their `main()` functions, wired up in `pyproject.toml`'s
  `[project.scripts]`).
- `examples/` — a synthetic config + sample XML, used by the README and as a
  smoke-test fixture. `examples/.xml-formats/xml.json` exercises config
  discovery by extension.
- `plans/done/extend-format-xml.md` — design history of `format_xml`'s feature
  set.

## Config discovery (`xml-format`)

Per input file, highest priority first: `--config-file FILE`, then
`--config-dir DIR` (`{DIR}/{ext}.json`), then a walk up from the CWD for
`.xml-formats/{ext}.json`, then the block-element default. `--no-config` forces
the default.

## Running

```bash
uv run xml-format --config-file examples/sample.json examples/sample.xml
uv run xml-identify '//tag' examples/sample.xml
```
