# xml-tools

Two small, format-agnostic XML command-line tools:

- **`xml-format`** — a configurable XML pretty-printer. All format-specific
  behavior (which tags are inline, code, compact, …) comes from a JSON config
  the caller supplies; it knows nothing about any particular XML vocabulary.
- **`xml-identify`** — stamps a `uuid` attribute onto every element matching an
  XPath expression.

Both depend only on the Python standard library plus
[`lxml`](https://lxml.de/).

## Install

Install the commands onto your `PATH` with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/<user>/xml-tools
```

Or run without a persistent install:

```bash
uvx --from git+https://github.com/<user>/xml-tools xml-format file.xml
```

For local development from a checkout:

```bash
uv tool install --editable .
```

## `xml-format`

```bash
xml-format [-i] [-q] [-f] [-c CONFIG_FILE | --config-dir DIR | --no-config] FILES...
```

Reads each file, pretty-prints it, and writes the result to stdout (or back to
the file with `-i`/`--inplace`).

```bash
# Format with an explicit config, printing to stdout:
xml-format --config-file examples/sample.json examples/sample.xml

# Format in place:
xml-format -i --config-file examples/sample.json examples/sample.xml

# No config found anywhere -> everything is a block element:
xml-format examples/sample.xml
```

### Choosing a config

A config is selected **per input file**. Resolution order, highest priority
first:

1. **`--config-file FILE`** (alias `-c`) — use exactly this JSON config,
   regardless of the input's extension.
2. **`--config-dir DIR`** — look up `{DIR}/{ext}.json` by the input file's
   extension, in that directory only (no walking).
3. **Default** — walk up from the current working directory looking for a
   `.xml-formats/` directory containing `{ext}.json` (e.g. `xml.json` for a
   `.xml` file). The nearest match wins. This is the same discovery model git
   uses to find `.git`.
4. **Nothing found** — fall back to the built-in default, which treats every
   element as a block element.

`--no-config` skips discovery entirely and forces the block-element default.

The upward search means a project can drop its configs in a `.xml-formats/`
directory at its root and run `xml-format` from anywhere inside the tree with
no flags — the right config is found by the input file's extension.

### Config format

The config is a JSON object. Every key is optional; omitted categories default
to empty.

```json
{
  "indent": 2,
  "width": 80,
  "inline": ["b", "link"],
  "code": ["snippet"],
  "preserve_whitespace": ["pre"],
  "one_line": ["cline"],
  "compact": ["tag"],
  "compound_code": {
    "program": { "code_children": ["preamble", "code", "postamble"] }
  },
  "rules": [
    { "tag": "pre", "parent": "datafile", "without_attr": "source", "treat_as": "code" }
  ],
  "formatters": {
    "code": ["clang-format", "-"]
  }
}
```

- **`indent`** — spaces per level (default 2).
- **`width`** — wrap width for fillable block content (default 80).
- **`inline`** — tags rendered inline within their parent's text flow.
- **`code`** — verbatim/code elements: dedented, wrapped in `CDATA` when needed.
- **`preserve_whitespace`** — elements whose internal whitespace is preserved.
- **`one_line`** — like `preserve_whitespace`, but no newlines around the close
  tag.
- **`compact`** — block elements that stay on one line when they fit.
- **`compound_code`** — a parent whose listed `code_children` are sibling code
  blocks sharing a common dedentation.
- **`rules`** — conditional overrides. Each rule matches on `tag`, `parent`,
  `has_attr`, and/or `without_attr`, and sets `treat_as` (`inline`, `code`,
  `preserve_whitespace`, or `block`). First match wins.
- **`formatters`** — map a tag (or the category `code`) to an external command
  that receives code on stdin and returns formatted code on stdout. Enabled
  with `-f`/`--format-code`; on non-zero exit the original text is kept.

## `xml-identify`

```bash
xml-identify [-i] XPATH FILES...
```

Adds a `uuid` attribute (a random UUID4) to every element matching `XPATH`
that doesn't already have one. Elements with a malformed existing `uuid` are
reported on stderr and left untouched. Writes to stdout unless `-i`/`--inplace`
is given.

```bash
xml-identify '//tag' examples/sample.xml
```

## License

[MIT](LICENSE)
