#!/usr/bin/env python3
"""Audit X-Drawing SVGs for basic filing-oriented safety constraints."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


FORBIDDEN = ("http://", "https://", "<script", "<image", "filter=", "linearGradient", "radialGradient")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a monochrome patent SVG")
    parser.add_argument("svg", type=Path)
    args = parser.parse_args()
    errors, warnings = [], []
    try:
        text = args.svg.read_text(encoding="utf-8-sig")
        root = ET.fromstring(text)
    except (OSError, ET.ParseError) as exc:
        print(f"ERROR: unreadable SVG: {exc}")
        return 2
    if not root.tag.endswith("svg"):
        errors.append("root element is not svg")
    if root.get("viewBox") != "0 0 210 297":
        errors.append("viewBox must be 0 0 210 297")
    lowered = text.lower()
    for item in FORBIDDEN:
        if item.lower() in lowered and item != "http://":
            errors.append(f"forbidden external/decorative construct: {item}")
    # Allow only the SVG namespace URL; reject any other URL.
    urls = re.findall(r'https?://[^"\'\s>]+', text)
    if any(url != "http://www.w3.org/2000/svg" for url in urls):
        errors.append("external URL found")
    colors = set(re.findall(r'#[0-9a-fA-F]{3,8}\b', text))
    if any(color.lower() not in {"#000", "#fff", "#000000", "#ffffff"} for color in colors):
        errors.append("non-monochrome color found")
    if "부호의 설명" not in text:
        warnings.append("symbol legend heading not found")
    if not re.search(r"【도\s*\d+】", text):
        warnings.append("figure number heading not found")
    if any(element.get("stroke-dasharray") for element in root.iter()
           if element.tag.split("}")[-1] in {"rect", "ellipse"}
           and element.get("class") != "system-group"):
        warnings.append("dashed component found; check its source note in the figure JSON")
    status = "PASS" if not errors else "FAIL"
    print(f"{status}: {args.svg}")
    for message in errors:
        print(f"ERROR: {message}")
    for message in warnings:
        print(f"WARNING: {message}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
