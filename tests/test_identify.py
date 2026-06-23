"""xml-identify: stamp uuid attributes onto XPath matches."""

import io
import uuid

from lxml import etree

from xml_tools import identify


def parse(path):
    return etree.parse(str(path)).getroot()


def test_adds_uuids_only_to_matching_elements(tmp_path):
    doc = tmp_path / "doc.xml"
    doc.write_text("<r><q>a</q><q>b</q><x>c</x></r>")

    identify.process_file(str(doc), "//q", inplace=True)

    root = parse(doc)
    qs = root.findall("q")
    assert all(q.get("uuid") for q in qs)
    # every stamped value is a well-formed uuid
    for q in qs:
        uuid.UUID(q.get("uuid"))
    assert root.find("x").get("uuid") is None  # non-matches untouched


def test_existing_valid_uuid_is_preserved(tmp_path):
    existing = "12345678-1234-1234-1234-123456789abc"
    doc = tmp_path / "doc.xml"
    doc.write_text(f'<r><q uuid="{existing}">a</q><q>b</q></r>')

    identify.process_file(str(doc), "//q", inplace=True)

    root = parse(doc)
    first, second = root.findall("q")
    assert first.get("uuid") == existing  # unchanged
    assert second.get("uuid") and second.get("uuid") != existing  # newly stamped


def test_malformed_uuid_warns_and_is_left_untouched(tmp_path, monkeypatch):
    # identify binds `stderr` at import (from sys import stderr), so redirect
    # that module-level name to capture its warnings.
    buf = io.StringIO()
    monkeypatch.setattr(identify, "stderr", buf)
    doc = tmp_path / "doc.xml"
    doc.write_text('<r><q uuid="not-a-uuid">a</q></r>')

    identify.process_file(str(doc), "//q", inplace=True)

    assert "malformed uuid" in buf.getvalue()
    assert parse(doc).find("q").get("uuid") == "not-a-uuid"  # not overwritten


def test_replace_gives_every_match_a_fresh_uuid(tmp_path):
    existing = "12345678-1234-1234-1234-123456789abc"
    doc = tmp_path / "doc.xml"
    doc.write_text(f'<r><q uuid="{existing}">a</q><q>b</q></r>')

    identify.process_file(str(doc), "//q", inplace=True, replace=True)

    root = parse(doc)
    first, second = root.findall("q")
    assert first.get("uuid") != existing  # the valid existing one is replaced
    uuid.UUID(first.get("uuid"))
    assert second.get("uuid")
    uuid.UUID(second.get("uuid"))


def test_replace_overwrites_a_malformed_uuid_without_warning(tmp_path, monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(identify, "stderr", buf)
    doc = tmp_path / "doc.xml"
    doc.write_text('<r><q uuid="not-a-uuid">a</q></r>')

    identify.process_file(str(doc), "//q", inplace=True, replace=True)

    stamped = parse(doc).find("q").get("uuid")
    assert stamped != "not-a-uuid"
    uuid.UUID(stamped)
    assert "malformed uuid" not in buf.getvalue()  # replaced, so no warning


def test_main_entry_point_stamps_in_place(tmp_path):
    doc = tmp_path / "doc.xml"
    doc.write_text("<r><item>a</item></r>")

    identify.main(["-i", "//item", str(doc)])

    assert parse(doc).find("item").get("uuid")


def test_main_replace_flag_rotates_existing_uuid(tmp_path):
    existing = "12345678-1234-1234-1234-123456789abc"
    doc = tmp_path / "doc.xml"
    doc.write_text(f'<r><item uuid="{existing}">a</item></r>')

    identify.main(["-i", "-r", "//item", str(doc)])

    assert parse(doc).find("item").get("uuid") != existing
