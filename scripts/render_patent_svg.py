#!/usr/bin/env python3
"""Render a validated monochrome patent figure from JSON to standalone SVG."""

from __future__ import annotations

import argparse
from html import escape
import json
import math
from pathlib import Path
import sys


KINDS = {"system", "flow", "state", "sequence"}
SHAPES = {"rect", "round", "ellipse"}
MAX_NODES = 20


def load_spec(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("figure specification must be a JSON object")
    if not isinstance(data.get("figure"), int) or data["figure"] < 1:
        raise ValueError("figure must be a positive integer")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise ValueError("title must be a non-empty string")
    if data.get("kind") not in KINDS:
        raise ValueError(f"kind must be one of: {', '.join(sorted(KINDS))}")
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError(f"nodes must contain 1-{MAX_NODES} objects")
    ids, refs = set(), set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError(f"node {index} must be an object")
        node_id, label, ref = node.get("id"), node.get("label"), str(node.get("ref", ""))
        if not isinstance(node_id, str) or not node_id.strip() or node_id in ids:
            raise ValueError(f"node {index} has a missing or duplicate id")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"node {node_id} needs a label")
        if not ref.isdigit() or ref in refs:
            raise ValueError(f"node {node_id} needs a unique numeric ref")
        if node.get("shape", "round") not in SHAPES:
            raise ValueError(f"node {node_id} has an unsupported shape")
        ids.add(node_id); refs.add(ref)
    edges = data.get("edges", [])
    if not isinstance(edges, list):
        raise ValueError("edges must be a list")
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict) or edge.get("from") not in ids or edge.get("to") not in ids:
            raise ValueError(f"edge {index} has an unknown endpoint")
        if edge["from"] == edge["to"]:
            raise ValueError(f"edge {index} cannot connect a node to itself")
        if "dashed" in edge and not isinstance(edge["dashed"], bool):
            raise ValueError(f"edge {index} dashed must be boolean")
    return data


def auto_layout(kind: str, nodes: list[dict]) -> list[dict]:
    result = [dict(node) for node in nodes]
    count = len(result)
    for index, node in enumerate(result):
        node.setdefault("w", 58 if kind != "flow" else 74)
        node.setdefault("h", 24)
        if "x" in node and "y" in node:
            continue
        if kind == "flow":
            node["x"] = 105 - node["w"] / 2
            node["y"] = 30 + index * min(38, 190 / max(1, count - 1))
        else:
            columns = 2 if count <= 8 else 3
            rows = math.ceil(count / columns)
            column = index % columns
            row = index // columns
            cell_w = 176 / columns
            cell_h = 190 / max(1, rows)
            node["x"] = 17 + column * cell_w + (cell_w - node["w"]) / 2
            node["y"] = 28 + row * cell_h + (cell_h - node["h"]) / 2
    for node in result:
        for key in ("x", "y", "w", "h"):
            if not isinstance(node.get(key), (int, float)):
                raise ValueError(f"node {node['id']} geometry {key} must be numeric")
        if node["x"] < 8 or node["y"] < 20 or node["x"] + node["w"] > 202 or node["y"] + node["h"] > 235:
            raise ValueError(f"node {node['id']} is outside the drawing area")
    return result


def boundary(a: dict, b: dict) -> tuple[float, float]:
    ax, ay = a["x"] + a["w"] / 2, a["y"] + a["h"] / 2
    bx, by = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
    dx, dy = bx - ax, by - ay
    if not dx and not dy:
        return ax, ay
    scale = min((a["w"] / 2) / abs(dx) if dx else 1e9, (a["h"] / 2) / abs(dy) if dy else 1e9)
    return ax + dx * scale, ay + dy * scale


def render(spec: dict) -> str:
    nodes = auto_layout(spec["kind"], spec["nodes"])
    by_id = {node["id"]: node for node in nodes}
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 210 297" width="210mm" height="297mm" role="img">',
        '<title>' + escape(f"도 {spec['figure']} {spec['title']}") + '</title>',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L8,4 L0,8 Z" fill="#000"/></marker></defs>',
        '<rect x="0" y="0" width="210" height="297" fill="#fff"/>',
        '<g fill="none" stroke="#000" stroke-width="0.7" stroke-linecap="round" stroke-linejoin="round">',
    ]
    for edge in spec.get("edges", []):
        source, target = by_id[edge["from"]], by_id[edge["to"]]
        x1, y1 = boundary(source, target); x2, y2 = boundary(target, source)
        dash = ' stroke-dasharray="3 2"' if edge.get("dashed") else ""
        parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" marker-end="url(#arrow)"{dash}/>')
        label = edge.get("label")
        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 2
            width = min(42, max(12, len(str(label)) * 3.2))
            parts.append(f'<rect x="{mx-width/2:.2f}" y="{my-4:.2f}" width="{width:.2f}" height="6" fill="#fff" stroke="none"/>')
            parts.append(f'<text x="{mx:.2f}" y="{my:.2f}" text-anchor="middle" fill="#000" stroke="none" font-family="Arial, sans-serif" font-size="3.2">{escape(str(label))}</text>')
    for node in nodes:
        shape = node.get("shape", "round")
        if shape == "ellipse":
            parts.append(f'<ellipse cx="{node["x"]+node["w"]/2:.2f}" cy="{node["y"]+node["h"]/2:.2f}" rx="{node["w"]/2:.2f}" ry="{node["h"]/2:.2f}" fill="#fff"/>')
        else:
            radius = 3 if shape == "round" else 0
            parts.append(f'<rect x="{node["x"]:.2f}" y="{node["y"]:.2f}" width="{node["w"]:.2f}" height="{node["h"]:.2f}" rx="{radius}" fill="#fff"/>')
        cx, cy = node["x"] + node["w"] / 2, node["y"] + node["h"] / 2
        parts.append(f'<text x="{cx:.2f}" y="{cy+1:.2f}" text-anchor="middle" fill="#000" stroke="none" font-family="Arial, sans-serif" font-size="4">{escape(node["label"])}</text>')
        parts.append(f'<text x="{node["x"]+node["w"]-2:.2f}" y="{node["y"]+5:.2f}" text-anchor="end" fill="#000" stroke="none" font-family="Arial, sans-serif" font-size="3.2">{escape(str(node["ref"]))}</text>')
    parts.append('</g>')
    parts.append(f'<text x="105" y="12" text-anchor="middle" fill="#000" font-family="Arial, sans-serif" font-size="5" font-weight="700">{escape(f"【도 {spec['figure']}】 {spec['title']}")}</text>')
    parts.append('<line x1="15" y1="246" x2="195" y2="246" stroke="#000" stroke-width="0.5"/>')
    parts.append('<text x="15" y="253" fill="#000" font-family="Arial, sans-serif" font-size="3.8" font-weight="700">부호의 설명</text>')
    for index, node in enumerate(sorted(nodes, key=lambda item: int(str(item["ref"])))):
        column, row = index % 2, index // 2
        x, y = 15 + column * 90, 260 + row * 6
        if y > 290:
            raise ValueError("symbol legend exceeds page; split the figure")
        parts.append(f'<text x="{x}" y="{y}" fill="#000" font-family="Arial, sans-serif" font-size="3.4">{escape(str(node["ref"]))}: {escape(node["label"])}</text>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an X-Drawing patent SVG")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        spec = load_spec(args.input)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render(spec), encoding="utf-8")
        print(args.output)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"x-drawing render error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
