"""Config loading and the per-file config resolution order.

Resolution order (highest first): --no-config, --config-file, --config-dir,
then the CWD-rooted upward search for .xml-formats/{ext}.json, then None
(block default).
"""

import json
from types import SimpleNamespace

from xml_tools import format_xml as F


def args(no_config=False, config_file=None, config_dir=None):
    return SimpleNamespace(no_config=no_config, config_file=config_file,
                           config_dir=config_dir)


# ── load_config ───────────────────────────────────────────────────────────────

def test_load_config_none_returns_a_copy_of_the_default():
    cfg = F.load_config(None)
    assert cfg == F.DEFAULT_CONFIG
    cfg["indent"] = 99
    assert F.DEFAULT_CONFIG["indent"] != 99  # must be a copy, not the original


def test_load_config_merges_and_coerces_lists_to_sets(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"indent": 4, "inline": ["em", "c"]}))
    cfg = F.load_config(str(p))
    assert cfg["indent"] == 4
    assert cfg["inline"] == {"em", "c"}
    assert cfg["width"] == F.DEFAULT_CONFIG["width"]  # untouched keys keep defaults


# ── resolve_config_path ───────────────────────────────────────────────────────

def test_config_file_takes_precedence_over_extension(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert F.resolve_config_path("doc.xml", args(config_file="/x/explicit.json")) \
        == "/x/explicit.json"


def test_config_dir_looks_up_by_extension(tmp_path):
    cfgdir = tmp_path / "formats"
    cfgdir.mkdir()
    (cfgdir / "xml.json").write_text("{}")
    assert F.resolve_config_path("doc.xml", args(config_dir=str(cfgdir))) \
        == str(cfgdir / "xml.json")


def test_config_dir_returns_none_when_no_matching_extension(tmp_path):
    cfgdir = tmp_path / "formats"
    cfgdir.mkdir()
    (cfgdir / "xml.json").write_text("{}")
    assert F.resolve_config_path("doc.quiz", args(config_dir=str(cfgdir))) is None


def test_no_config_beats_everything(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a = args(no_config=True, config_file="/x/explicit.json")
    assert F.resolve_config_path("doc.xml", a) is None


def test_default_discovers_dot_xml_formats_by_walking_up(tmp_path, monkeypatch):
    formats = tmp_path / ".xml-formats"
    formats.mkdir()
    (formats / "xml.json").write_text("{}")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert F.resolve_config_path("doc.xml", args()) == str(formats / "xml.json")


def test_default_returns_none_when_nothing_is_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert F.resolve_config_path("doc.xml", args()) is None


def test_extensionless_input_discovers_nothing(tmp_path, monkeypatch):
    formats = tmp_path / ".xml-formats"
    formats.mkdir()
    (formats / ".json").write_text("{}")
    monkeypatch.chdir(tmp_path)
    assert F.resolve_config_path("Makefile", args()) is None


# ── main() round trip ─────────────────────────────────────────────────────────

def test_main_inplace_formats_with_discovered_config(tmp_path, monkeypatch):
    (tmp_path / ".xml-formats").mkdir()
    (tmp_path / ".xml-formats" / "xml.json").write_text(json.dumps({"inline": ["em"]}))
    doc = tmp_path / "doc.xml"
    doc.write_text("<p>Hi <em>there</em></p>")
    monkeypatch.chdir(tmp_path)

    F.main(["-i", "-q", "doc.xml"])

    text = doc.read_text()
    assert text.startswith('<?xml version="1.0" encoding="utf-8"?>')
    assert "<p>Hi <em>there</em></p>" in text  # em kept inline by the discovered config
