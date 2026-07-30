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


def test_block_child_in_mixed_content_is_idempotent():
    # A non-inline child in the middle of prose: the whitespace at the
    # text/child boundaries must not accumulate on repeated formatting.
    cfg = make_cfg()
    once = fmt("<p>alpha <weird>x</weird> beta\n  gamma <weird>y</weird> delta</p>", cfg)
    assert fmt(once, cfg) == once
    assert "\n\n" not in once  # no blank lines inside the prose


def test_tail_after_block_child_lands_on_an_indented_line():
    out = fmt("<p>alpha <weird>x</weird> beta</p>", make_cfg())
    assert "<weird>x</weird>\n  beta" in out


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


def test_code_element_child_survives_formatting():
    # A code element whose content comes from an element child (e.g. an
    # xi:include pulling in a code file) must keep the child, not flatten
    # the element to its (empty) text content.
    xml = ('<pre xmlns:xi="http://www.w3.org/2001/XInclude">\n'
           '  <xi:include parse="text" href="f.java" />\n'
           '</pre>')
    cfg = make_cfg(code=["pre"])
    out = fmt(xml, cfg)
    assert '<xi:include parse="text" href="f.java" />' in out
    assert fmt(out, cfg) == out  # and the fallback rendering is idempotent


def test_code_whitespace_only_lines_dont_defeat_dedenting():
    # A line of stray spaces, shallower than the code's real margin, must not
    # be counted when computing the dedent, and is normalized to a truly
    # empty line so formatting is stable.
    cfg = make_cfg(code=["code"])
    out = fmt("<code>\n    a\n  \n    b\n</code>", cfg)
    assert "\n  a\n" in out and "\n  b\n" in out  # margin of 4 reduced to indent
    assert "\n\n" in out                          # junk line now truly empty
    assert fmt(out, cfg) == out


def test_compound_code_whitespace_only_lines_dont_defeat_dedenting():
    cfg = make_cfg(compound_code={"program": {"code_children": ["code"]}})
    prog = "<program><code>\n    a\n  \n    b\n</code></program>"
    once = fmt(prog, cfg)
    assert "\n    a\n" in once  # code child at indent 4 under program
    assert fmt(once, cfg) == once


def test_code_comment_child_survives_formatting():
    out = fmt("<pre>x = 1\n<!-- keep me -->\ny = 2</pre>", make_cfg(code=["pre"]))
    assert "<!-- keep me -->" in out
    assert "x = 1" in out
    assert "y = 2" in out


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
