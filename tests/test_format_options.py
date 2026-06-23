"""Exercise each configurable option of the XML formatter.

The config keys covered: indent, width, inline, code, preserve_whitespace,
one_line, compact, compound_code, rules, formatters (plus the no-config /
block-everything default).
"""

import sys

from lxml import etree

from xml_tools import format_xml as F


def make_cfg(**overrides):
    """Build a config dict the way load_config would, from keyword overrides."""
    cfg = dict(F.DEFAULT_CONFIG)
    cfg.update(overrides)
    for key in ("inline", "code", "preserve_whitespace", "one_line", "compact"):
        cfg[key] = set(cfg[key])
    return cfg


def fmt(xml, cfg=None, format_enabled=False):
    """Format a single XML element with the given config, like reformat does."""
    cfg = dict(cfg if cfg is not None else make_cfg())
    cfg["_format_enabled"] = format_enabled
    root = etree.fromstring(xml.encode())
    return F.serialize_element(root, cfg=cfg).strip()


# ── indent ────────────────────────────────────────────────────────────────────

def test_indent_controls_nesting_width():
    assert fmt("<a><b>x</b></a>", make_cfg(indent=4)) == "<a>\n    <b>x</b>\n</a>"
    assert fmt("<a><b>x</b></a>", make_cfg(indent=2)) == "<a>\n  <b>x</b>\n</a>"


# ── width ─────────────────────────────────────────────────────────────────────

def test_width_wraps_long_block_content():
    out = fmt("<p>one two three four five six seven eight nine ten</p>",
              make_cfg(width=20))
    lines = out.splitlines()
    assert len(lines) > 1, "narrow width should wrap onto multiple lines"
    assert all(len(line) <= 20 for line in lines)


def test_width_keeps_short_content_on_one_line():
    out = fmt("<p>one two three four five</p>", make_cfg(width=200))
    assert out == "<p>one two three four five</p>"


# ── inline ────────────────────────────────────────────────────────────────────

def test_inline_elements_stay_in_text_flow():
    out = fmt("<p>Hello <em>there</em> world</p>", make_cfg(inline=["em"]))
    assert out == "<p>Hello <em>there</em> world</p>"


def test_non_inline_child_breaks_onto_its_own_line():
    # With the default (block) config, <em> is not inline.
    out = fmt("<p>Hello <em>x</em></p>")
    assert "\n  <em>x</em>" in out


# ── code ──────────────────────────────────────────────────────────────────────

def test_code_block_without_special_chars_has_no_cdata():
    out = fmt("<code>x = 1</code>", make_cfg(code=["code"]))
    assert out == "<code>\n  x = 1\n</code>"
    assert "CDATA" not in out


def test_code_block_with_special_chars_is_wrapped_in_cdata():
    out = fmt("<code>a &lt; b</code>", make_cfg(code=["code"]))
    assert "<![CDATA[" in out
    assert "]]>" in out
    assert "a < b" in out  # unescaped inside CDATA


# ── preserve_whitespace ───────────────────────────────────────────────────────

def test_preserve_whitespace_keeps_internal_layout():
    out = fmt("<pre>a\n  b\nc</pre>", make_cfg(preserve_whitespace=["pre"]))
    assert out == "<pre>a\n  b\nc\n</pre>"


# ── one_line ──────────────────────────────────────────────────────────────────

def test_one_line_preserves_whitespace_without_surrounding_newlines():
    cfg = make_cfg(preserve_whitespace=["cline"], one_line=["cline"])
    out = fmt("<cline>a  b</cline>", cfg)
    assert out == "<cline>a  b</cline>"
    assert "\n" not in out


def test_preserve_whitespace_without_one_line_breaks_the_close_tag():
    # Same content, but not in one_line: the close tag drops to its own line.
    cfg = make_cfg(preserve_whitespace=["cline"])
    out = fmt("<cline>a  b</cline>", cfg)
    assert out.endswith("\n</cline>")


# ── compact ───────────────────────────────────────────────────────────────────

def test_compact_siblings_have_no_blank_line_between_them():
    out = fmt("<list><item>a</item><item>b</item></list>", make_cfg(compact=["item"]))
    assert out == "<list>\n  <item>a</item>\n  <item>b</item>\n</list>"


def test_non_compact_siblings_are_separated_by_a_blank_line():
    out = fmt("<list><thing>a</thing><thing>b</thing></list>")
    assert "</thing>\n\n  <thing>" in out


# ── compound_code ─────────────────────────────────────────────────────────────

def test_compound_code_shares_dedentation_across_children():
    cfg = make_cfg(compound_code={"program": {"code_children": ["preamble", "code"]}})
    # preamble indented 4, code indented 8: common (4) is stripped, so the
    # 4-space difference between them is preserved under the program element.
    prog = "<program><preamble>    import x</preamble><code>        run()</code></program>"
    out = fmt(prog, cfg)
    assert "\n    import x\n" in out   # preamble: 4 spaces
    assert "\n        run()\n" in out  # code: 8 spaces (relative indent kept)


def test_compound_code_parent_with_only_text_is_handled_normally():
    # The compound layout only kicks in when the parent has element children;
    # a text-only parent (not also in `code`) is just a normal block element.
    cfg = make_cfg(compound_code={"program": {"code_children": ["code"]}})
    out = fmt("<program>just text</program>", cfg)
    assert out == "<program>just text</program>"


# ── rules (conditional classification) ────────────────────────────────────────

RULE = [{"tag": "pre", "parent": "datafile", "without_attr": "source", "treat_as": "code"}]


def test_rule_promotes_matching_element_to_code():
    out = fmt("<datafile><pre>a&lt;b</pre></datafile>", make_cfg(rules=RULE))
    assert "<![CDATA[" in out  # treated as code -> CDATA for the '<'


def test_rule_skipped_when_without_attr_present():
    out = fmt('<datafile><pre source="f">hi</pre></datafile>', make_cfg(rules=RULE))
    assert "CDATA" not in out
    assert '<pre source="f">hi</pre>' in out


def test_rule_skipped_when_parent_does_not_match():
    # Same rule, but <pre> is not inside <datafile>: stays a block element.
    out = fmt("<pre>a&lt;b</pre>", make_cfg(rules=RULE))
    assert "CDATA" not in out


# ── formatters ────────────────────────────────────────────────────────────────

UPPER = [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())"]


def test_formatter_runs_when_enabled():
    cfg = make_cfg(code=["code"], formatters={"code": UPPER})
    assert "HELLO" in fmt("<code>hello</code>", cfg, format_enabled=True)


def test_formatter_is_off_by_default():
    cfg = make_cfg(code=["code"], formatters={"code": UPPER})
    assert "hello" in fmt("<code>hello</code>", cfg, format_enabled=False)


# ── no-config default ─────────────────────────────────────────────────────────

def test_default_config_treats_everything_as_a_block():
    # No categories configured: every child element gets its own block line.
    out = fmt("<doc><a>1</a><b>2</b></doc>")
    assert "\n  <a>1</a>" in out
    assert "\n  <b>2</b>" in out
