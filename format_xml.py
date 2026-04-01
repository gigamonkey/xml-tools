#!/usr/bin/env python

"""
General-purpose XML formatter.

Formats XML files with consistent indentation, text wrapping, and optional
CDATA sections for code elements. Element categories (inline, code,
preserve_whitespace, one_line, compact) are specified via a JSON config file;
anything not listed is treated as a block element.

Config JSON example:
{
  "indent": 2,
  "width": 80,
  "inline": ["em", "c", "url"],
  "code": ["code"],
  "preserve_whitespace": ["pre"],
  "one_line": ["cline"],
  "compact": ["item"],
  "compound_code": {
    "program": {
      "code_children": ["preamble", "code", "postamble"]
    }
  },
  "rules": [
    {
      "tag": "pre",
      "parent": "datafile",
      "without_attr": "source",
      "treat_as": "code"
    }
  ],
  "formatters": {
    "code": ["java", "-jar", "google-java-format.jar", "-a", "-"]
  }
}
"""

import json
import os
import re
import subprocess
from argparse import ArgumentParser
from sys import stderr, stdout
from textwrap import fill, dedent, indent

from lxml import etree
from xml.sax.saxutils import escape, quoteattr


# ── Configuration ────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "indent": 2,
    "width": 80,
    "inline": set(),
    "code": set(),
    "preserve_whitespace": set(),
    "one_line": set(),
    "compact": set(),
    "compound_code": {},
    "rules": [],
    "formatters": {},
}

DEFAULT_NS = {"xml": "http://www.w3.org/XML/1998/namespace"}


def load_config(path):
    if path is None:
        return dict(DEFAULT_CONFIG)
    with open(path) as f:
        user = json.load(f)
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(user)
    # Ensure list fields are sets for fast lookup.
    for key in ("inline", "code", "preserve_whitespace", "one_line", "compact"):
        cfg[key] = set(cfg[key])
    # Ensure dict/list fields have correct types.
    if not isinstance(cfg["compound_code"], dict):
        cfg["compound_code"] = {}
    if not isinstance(cfg["rules"], list):
        cfg["rules"] = []
    if not isinstance(cfg["formatters"], dict):
        cfg["formatters"] = {}
    return cfg


# ── Helpers ──────────────────────────────────────────────────────────────────

def indentation(level, cfg):
    return " " * (cfg["indent"] * level)


def open_tag(elem, ns, empty=False):
    s = f"<{namespaced(elem.tag, ns)}"
    for name, value in elem.attrib.items():
        s += f" {fmt_attr(name, value, ns)}"
    for prefix, url in elem.nsmap.items():
        if prefix not in ns:
            s += f' xmlns:{prefix}="{url}"'
    if empty:
        s += " /"
    s += ">"
    return s


def fmt_attr(name, value, ns):
    return f"{namespaced(name, ns)}={quoteattr(value)}"


def namespaced(name, ns):
    reverse = {v: k for k, v in ns.items()}
    if name.startswith("{"):
        uri, local = name[1:].split("}")
        prefix = reverse.get(uri)
        if prefix:
            return f"{prefix}:{local}"
        else:
            print(f"Unknown namespace {uri}", file=stderr)
            return name
    return name


def close_tag(elem, ns):
    return f"</{namespaced(elem.tag, ns)}>"


# ── Predicates ───────────────────────────────────────────────────────────────

def is_just_text(elem):
    return len(elem) == 0


def is_multiline(text):
    return len(text.split("\n")) > 1


def to_text(elem):
    return etree.tostring(elem, encoding="unicode", method="text")


def is_inline(elem, cfg):
    return elem.tag in cfg["inline"]


def is_code(elem, cfg):
    return elem.tag in cfg["code"]


def is_empty(elem):
    return (elem.text or "").strip() == "" and not len(elem)


def preserve_whitespace(elem, cfg):
    return elem.tag in cfg["preserve_whitespace"]


def is_oneline(elem, cfg):
    return elem.tag in cfg["one_line"]


def is_compact(elem, cfg):
    return elem.tag in cfg["compact"]


def is_compound_code(elem, cfg):
    return elem.tag in cfg["compound_code"]


def empty_text(x):
    return (x or "").strip() == ""


def singleton_child(elem):
    return len(elem) == 1 and empty_text(elem.text) and empty_text(elem[0].tail)


def wrappable(elem, cfg):
    return not preserve_whitespace(elem, cfg) and (
        is_inline(elem, cfg) or all(is_inline(e, cfg) for e in elem)
    )


# ── Conditional classification rules ────────────────────────────────────────

def apply_rules(elem, cfg):
    """Check conditional rules and return the overridden category, or None."""
    for rule in cfg["rules"]:
        if rule.get("tag") and rule["tag"] != elem.tag:
            continue
        if rule.get("parent"):
            parent = elem.getparent()
            if parent is None or parent.tag != rule["parent"]:
                continue
        if rule.get("has_attr"):
            if rule["has_attr"] not in elem.attrib:
                continue
        if rule.get("without_attr"):
            if rule["without_attr"] in elem.attrib:
                continue
        return rule.get("treat_as")
    return None


# ── Dedentation utilities ───────────────────────────────────────────────────

def measure_indentation(line):
    return float("inf") if line == "" else len(line) - len(dedent(line))


def dedent_amount(text):
    return min(measure_indentation(line) for line in text.split("\n"))


def common_indentation(texts):
    return min(dedent_amount(text) for text in texts)


def dedent_by(text, amount):
    if amount is None:
        return dedent(text)
    return "\n".join(
        line[amount:] if len(line) > 0 else line for line in text.split("\n")
    )


# ── Formatter plugins ───────────────────────────────────────────────────────

def maybe_formatted(text, elem, cfg):
    """Pipe text through an external formatter if one is configured."""
    formatters = cfg.get("formatters", {})
    if not formatters or not cfg.get("_format_enabled"):
        return text

    # Look up formatter by tag name first, then by category "code".
    cmd = formatters.get(elem.tag) or formatters.get("code")
    if not cmd:
        return text

    result = subprocess.run(
        cmd,
        capture_output=True,
        input=text,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"Couldn't format\n{text}\n", file=stderr)
        return text
    return result.stdout


# ── Renderers ────────────────────────────────────────────────────────────────

def render_inline(elem, ns, cfg):
    if is_empty(elem):
        return open_tag(elem, ns, empty=True)

    s = open_tag(elem, ns)

    if is_just_text(elem):
        s += escape(elem.text.strip())
    else:
        if elem.text and elem.text.strip():
            s += escape(elem.text)

    for child in elem:
        s += render_inline(child, ns | elem.nsmap, cfg)
        if child.tail:
            s += escape(child.tail)

    s += close_tag(elem, ns)
    return s


def render_verbatim_text(elem, ns, level, cfg, dedentation=None):
    """Render a code/verbatim element: dedent, optionally format, wrap in CDATA
    if needed."""
    indent1 = indentation(level, cfg)
    indent2 = indentation(level + 1, cfg)

    text = re.sub(
        r"^(\s*\n)*",
        "",
        maybe_formatted(
            dedent_by(to_text(elem), dedentation).rstrip(),
            elem,
            cfg,
        ),
    )
    needs_cdata = any(e in text for e in "&<>")

    content = f"\n{indent1}{open_tag(elem, ns)}\n"

    if needs_cdata:
        content += f"{indent2}<![CDATA[\n"

    content += indent(text, indent2)

    if needs_cdata:
        content += f"\n{indent2}]]>"

    content += f"\n{indent1}{close_tag(elem, ns)}\n"
    return content


def render_compound_code(elem, ns, level, cfg):
    """Render a compound code element whose children share common
    dedentation."""
    compound_cfg = cfg["compound_code"][elem.tag]
    code_child_tags = set(compound_cfg.get("code_children", []))

    if is_just_text(elem):
        # Simple element that directly contains text.
        return render_verbatim_text(elem, ns, level, cfg)

    content = f"\n{indentation(level, cfg)}{open_tag(elem, ns)}\n"

    # Separate code children from other children.
    code_children = [c for c in elem if c.tag in code_child_tags]
    other_children = [c for c in elem if c.tag not in code_child_tags]

    if code_children:
        d = common_indentation(to_text(x).rstrip() for x in code_children)
        for c in code_children:
            content += render_verbatim_text(c, ns, level + 1, cfg, d)

    if other_children:
        for o in other_children:
            content += render_verbatim_text(o, ns, level + 1, cfg)

    content += f"\n{indentation(level, cfg)}{close_tag(elem, ns)}\n"
    return content


def render_comment(elem, level, cfg):
    return f"{elem}{elem.tail or ''}".rstrip()


def render_block(elem, ns, level, cfg):
    tag = f"\n{indentation(level, cfg)}{open_tag(elem, ns)}"
    width = cfg["width"]

    if is_empty(elem):
        return f"\n{indentation(level, cfg)}{open_tag(elem, ns, empty=True)}"

    content = ""

    if elem.text and elem.text.strip():
        content += escape(elem.text.lstrip())

    if len(elem) > 0:
        if is_inline(elem[0], cfg):
            content = re.sub(r"\s+$", " ", content)
        else:
            content = content.rstrip()

    for child in elem:
        content += serialize_element(child, ns | elem.nsmap, level + 1, cfg)
        if child.tail and child.tail.strip():
            content += escape(child.tail)
        elif child.tail and not child.tail.strip() and is_inline(child, cfg):
            content += " "

    if wrappable(elem, cfg):
        oneline = (
            f"{tag}{re.sub(r'(?s)\\s+', ' ', content).strip()}{close_tag(elem, ns)}"
        )

        if len(oneline) - 1 <= width:  # -1 for the leading newline.
            return oneline if is_compact(elem, cfg) else f"{oneline}\n"

        if not singleton_child(elem):
            filled = fill_with_indent(content, indentation(level + 1, cfg), width)
            return f"{tag}\n{filled}\n{indentation(level, cfg)}{close_tag(elem, ns)}\n"

    return f"{tag}\n{indentation(level + 1, cfg)}{content.strip()}\n{indentation(level, cfg)}{close_tag(elem, ns)}\n"


def render_with_whitespace(elem, ns, level, cfg):
    if is_empty(elem):
        return f"\n{indentation(level, cfg)}{open_tag(elem, ns, empty=True)}"

    s = f"\n{indentation(level, cfg)}{open_tag(elem, ns)}"
    if elem.text and len(elem.text) > 0:
        s += escape(elem.text)
    for child in elem:
        s += render_child_with_whitespace(child, ns | elem.nsmap)
        if child.tail and len(child.tail) > 0:
            s += child.tail

    s = s.rstrip()

    if not is_oneline(elem, cfg):
        s += f"\n{indentation(level, cfg)}"

    s += close_tag(elem, ns)

    if not is_oneline(elem, cfg):
        s += "\n"

    return s


def render_child_with_whitespace(elem, ns):
    s = open_tag(elem, ns)
    if elem.text and len(elem.text) > 0:
        s += escape(elem.text)
    for child in elem:
        s += render_child_with_whitespace(child, ns | elem.nsmap)
        if child.tail and len(child.tail) > 0:
            s += child.tail
    s += close_tag(elem, ns)
    return s


# ── Text wrapping ────────────────────────────────────────────────────────────

def clean_text(s):
    return re.sub(r"\s+", " ", s.strip())


def fill_with_indent(text, i, width):
    return fill(
        clean_text(text),
        width=width,
        initial_indent=i,
        subsequent_indent=i,
        break_long_words=False,
        break_on_hyphens=False,
    )


# ── Main serializer ─────────────────────────────────────────────────────────

def serialize_element(elem, ns=DEFAULT_NS, level=0, cfg=DEFAULT_CONFIG):
    if not isinstance(elem.tag, str):
        return render_comment(elem, level, cfg)

    # Check conditional rules for category override.
    override = apply_rules(elem, cfg)

    if override == "inline":
        return render_inline(elem, ns, cfg)
    elif override == "code":
        return render_verbatim_text(elem, ns, level, cfg)
    elif override == "preserve_whitespace":
        return render_with_whitespace(elem, ns, level, cfg)
    elif override == "block":
        return render_block(elem, ns, level, cfg)
    elif override is not None:
        # Unknown override; treat as block.
        return render_block(elem, ns, level, cfg)

    # Normal tag-based dispatch.
    if is_inline(elem, cfg):
        return render_inline(elem, ns, cfg)
    elif is_compound_code(elem, cfg) and not is_just_text(elem):
        return render_compound_code(elem, ns, level, cfg)
    elif is_code(elem, cfg):
        return render_verbatim_text(elem, ns, level, cfg)
    elif preserve_whitespace(elem, cfg):
        return render_with_whitespace(elem, ns, level, cfg)
    else:
        return render_block(elem, ns, level, cfg)


def document_elements(root):
    top_level = []
    e = root
    while e is not None:
        top_level.append(e)
        e = e.getprevious()
    top_level.reverse()
    e = root.getnext()
    while e is not None:
        top_level.append(e)
        e = e.getnext()
    return top_level


def reformat(filename, inplace, cfg):
    root = etree.parse(filename).getroot()
    f = open(filename, mode="w") if inplace else stdout
    print('<?xml version="1.0" encoding="utf-8"?>', file=f)
    for e in document_elements(root):
        print(serialize_element(e, cfg=cfg).rstrip(), file=f)
    if inplace:
        f.close()


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = ArgumentParser(
        prog="format_xml",
        description="General-purpose XML formatter with configurable element categories.",
    )

    parser.add_argument(
        "-i", "--inplace", action="store_true", help="Reformat in place"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress progress output"
    )
    parser.add_argument(
        "-c", "--config", default=None, help="Path to JSON config file"
    )
    parser.add_argument(
        "-f", "--format-code", action="store_true",
        help="Enable external code formatting via configured formatters"
    )
    parser.add_argument("files", nargs="*", help="Files to reformat")

    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    formats_dir = os.path.join(script_dir, ".xml-formats")

    for filename in args.files:
        if args.config:
            cfg = load_config(args.config)
        else:
            ext = os.path.splitext(filename)[1].lstrip(".")
            auto_config = os.path.join(formats_dir, f"{ext}.json")
            cfg = load_config(auto_config if os.path.exists(auto_config) else None)
        cfg["_format_enabled"] = args.format_code

        if not args.quiet:
            print(f"{filename} ... ", file=stderr, end="")
        reformat(filename, args.inplace, cfg)
        if not args.quiet:
            print("ok.", file=stderr)
