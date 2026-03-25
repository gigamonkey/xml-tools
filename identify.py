#!/usr/bin/env python

"""Add uuid attributes to XML elements matching an XPath expression."""

import re
import uuid
from argparse import ArgumentParser
from sys import stderr, stdout

from lxml import etree


UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def process_file(filename, xpath, inplace):
    tree = etree.parse(filename)
    matches = tree.xpath(xpath)
    changed = False

    for elem in matches:
        existing = elem.get("uuid")
        if existing is not None:
            if not UUID_RE.match(existing):
                print(
                    f"WARNING: {filename}:{elem.sourceline}: <{elem.tag}> has malformed uuid: {existing!r}",
                    file=stderr,
                )
        else:
            elem.set("uuid", str(uuid.uuid4()))
            changed = True

    if changed:
        if inplace:
            tree.write(filename, xml_declaration=True, encoding="utf-8")
            print(f"{filename}: updated", file=stderr)
        else:
            tree.write(stdout.buffer, xml_declaration=True, encoding="utf-8")


if __name__ == "__main__":
    parser = ArgumentParser(
        prog="identify",
        description="Add uuid attributes to XML elements matching an XPath expression.",
    )
    parser.add_argument("-i", "--inplace", action="store_true", help="Modify files in place")
    parser.add_argument("xpath", help="XPath expression to match elements")
    parser.add_argument("files", nargs="+", help="XML files to process")

    args = parser.parse_args()

    for filename in args.files:
        process_file(filename, args.xpath, args.inplace)
