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
STYLE_PRESETS = {
    "default": {"stroke_width": "0.7", "label_size": "4", "ref_size": "3.2", "edge_dash": "3 2"},
    "compact": {"stroke_width": "0.7", "label_size": "3.6", "ref_size": "3.2", "edge_dash": "2 1.5"},
}
CORNERS = {"round", "square"}
REFERENCE_STYLES = {"leader", "inside"}
LAYOUTS = {"legacy", "directed"}
EDGE_STYLES = {"solid", "dashed", "dotted", "blocked"}
FONT_FAMILY = "Malgun Gothic, Apple SD Gothic Neo, Noto Sans CJK KR, Arial, sans-serif"


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
    if data.get("corners", "round") not in CORNERS:
        raise ValueError("corners must be round or square")
    if data.get("style", "default") not in STYLE_PRESETS:
        raise ValueError("style must be default or compact")
    if data.get("reference_style", "inside") not in REFERENCE_STYLES:
        raise ValueError("reference_style must be leader or inside")
    if data.get("layout", "legacy") not in LAYOUTS:
        raise ValueError("layout must be legacy or directed")
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
        if "optional" in node and not isinstance(node["optional"], bool):
            raise ValueError(f"node {node_id} optional must be boolean")
        if node.get("optional") and (not isinstance(node.get("source"), str) or not node["source"].strip()):
            raise ValueError(f"node {node_id} marked optional needs a non-empty source note")
        for field in ("hatch", "show_ref"):
            if field in node and not isinstance(node[field], bool):
                raise ValueError(f"node {node_id} {field} must be boolean")
        if node.get("show_ref") is False and not node.get("subparts") and f"({ref})" not in label:
            raise ValueError(f"node {node_id} hides its reference numeral without showing it in the label")
        ids.add(node_id); refs.add(ref)
        subparts = node.get("subparts", [])
        if not isinstance(subparts, list):
            raise ValueError(f"node {node_id} subparts must be a list")
        for subpart in subparts:
            if not isinstance(subpart, dict):
                raise ValueError(f"node {node_id} subpart must be an object")
            subref, sublabel = str(subpart.get("ref", "")), subpart.get("label")
            if not subref.isdigit() or subref in refs or not isinstance(sublabel, str) or not sublabel.strip():
                raise ValueError(f"node {node_id} subpart needs a unique numeric ref and label")
            refs.add(subref)
    groups = data.get("groups", [])
    if not isinstance(groups, list):
        raise ValueError("groups must be a list")
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("label"), str) or not group["label"].strip():
            raise ValueError("group needs a label")
        group_ref = str(group.get("ref", ""))
        if not group_ref.isdigit() or group_ref in refs:
            raise ValueError("group needs a unique numeric ref")
        refs.add(group_ref)
        for key in ("x", "y", "w", "h"):
            if not isinstance(group.get(key), (int, float)) or isinstance(group[key], bool):
                raise ValueError(f"group {group_ref} geometry {key} must be numeric")
        if (group["x"] < 8 or group["y"] < 20 or group["w"] <= 0 or group["h"] <= 0
                or group["x"] + group["w"] > 202 or group["y"] + group["h"] > 235):
            raise ValueError(f"group {group_ref} is outside the drawing area")
        if "dashed" in group and not isinstance(group["dashed"], bool):
            raise ValueError(f"group {group_ref} dashed must be boolean")
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
        if edge.get("style", "solid") not in EDGE_STYLES:
            raise ValueError(f"edge {index} has an unsupported style")
        if "arrow" in edge and not isinstance(edge["arrow"], bool):
            raise ValueError(f"edge {index} arrow must be boolean")
        via = edge.get("via", [])
        if not isinstance(via, list) or len(via) > 8:
            raise ValueError(f"edge {index} via must be a list of up to eight points")
        for point in via:
            if (not isinstance(point, list) or len(point) != 2
                    or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in point)
                    or not 8 <= point[0] <= 202 or not 20 <= point[1] <= 235):
                raise ValueError(f"edge {index} has an invalid via point")
    return data


def path_order(nodes: list[dict], edges: list[dict]) -> list[str] | None:
    """Return node IDs for a single directed chain, or None for any other graph."""
    if len(edges) != len(nodes) - 1:
        return None
    incoming = {node["id"]: 0 for node in nodes}
    outgoing = {}
    for edge in edges:
        source, target = edge["from"], edge["to"]
        incoming[target] += 1
        if incoming[target] > 1 or source in outgoing:
            return None
        outgoing[source] = target
    starts = [node_id for node_id, degree in incoming.items() if degree == 0]
    if len(starts) != 1:
        return None
    order = [starts[0]]
    while order[-1] in outgoing and len(order) < len(nodes):
        order.append(outgoing[order[-1]])
    return order if len(order) == len(nodes) and len(set(order)) == len(nodes) else None


def auto_layout(kind: str, nodes: list[dict], corners: str = "round", edges: list[dict] | None = None,
                reference_style: str = "inside", layout: str = "legacy", ref_size: float = 3.2) -> list[dict]:
    result = [dict(node) for node in nodes]
    count = len(result)
    manual = ["x" in node and "y" in node for node in result]
    if layout == "directed" and any("x" in node or "y" in node for node in result) and not all(manual):
        raise ValueError("directed layout requires all or no nodes to have x and y")
    chain = (path_order(result, edges or []) if layout == "directed" and not any(manual)
             and kind == "system" and 3 <= count <= 6 else None)
    chain_index = {node_id: index for index, node_id in enumerate(chain or [])}
    for index, node in enumerate(result):
        node.setdefault("shape", "rect" if corners == "square" else "round")
        node.setdefault("w", 58 if kind != "flow" else 74)
        node.setdefault("h", 20 if kind == "flow" and layout == "directed" else 24)
        if "x" in node and "y" in node:
            continue
        if (kind == "flow" and layout == "directed") or chain:
            position = chain_index[node["id"]] if chain else index
            height = node["h"]
            max_height = max(item.get("h", 20 if kind == "flow" else 24) for item in result)
            spacing = min(38, (200 - max_height) / max(1, count - 1))
            group_height = max_height + (count - 1) * spacing
            node["x"] = 105 - node["w"] / 2
            node["y"] = (260 - group_height) / 2 + position * spacing + (max_height - height) / 2
        elif kind == "flow":
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
        if reference_style == "leader" and node["y"] - 6 - ref_size < 17:
            raise ValueError(f"reference number for {node['id']} is too close to the figure heading")
    for index, left in enumerate(result):
        for right in result[index + 1:]:
            if (left["x"] < right["x"] + right["w"] and right["x"] < left["x"] + left["w"]
                    and left["y"] < right["y"] + right["h"] and right["y"] < left["y"] + left["h"]):
                raise ValueError(f"nodes {left['id']} and {right['id']} overlap; split or reposition the figure")
            if reference_style == "leader":
                for owner, other in ((left, right), (right, left)):
                    label_right = owner["x"] + owner["w"] - 6
                    label_left = label_right - len(str(owner["ref"])) * ref_size * 0.7 - 1
                    label_top = owner["y"] - 6 - ref_size
                    if (other["x"] < label_right + 4 and label_left < other["x"] + other["w"]
                            and other["y"] < owner["y"] and label_top < other["y"] + other["h"]):
                        raise ValueError(f"reference leader for {owner['id']} overlaps {other['id']}; reposition or split the figure")
    return result


def boundary(a: dict, b: dict) -> tuple[float, float]:
    ax, ay = a["x"] + a["w"] / 2, a["y"] + a["h"] / 2
    bx, by = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
    dx, dy = bx - ax, by - ay
    if not dx and not dy:
        return ax, ay
    scale = min((a["w"] / 2) / abs(dx) if dx else 1e9, (a["h"] / 2) / abs(dy) if dy else 1e9)
    return ax + dx * scale, ay + dy * scale


def path_midpoint(points: list[tuple[float, float]]) -> tuple[float, float]:
    segments = [(a, b, math.hypot(b[0] - a[0], b[1] - a[1])) for a, b in zip(points, points[1:])]
    distance = sum(length for _, _, length in segments) / 2
    for start, end, length in segments:
        if distance <= length and length:
            fraction = distance / length
            return start[0] + (end[0] - start[0]) * fraction, start[1] + (end[1] - start[1]) * fraction
        distance -= length
    return points[-1]


def render(spec: dict) -> str:
    style = STYLE_PRESETS[spec.get("style", "default")]
    reference_style = spec.get("reference_style", "inside")
    nodes = auto_layout(spec["kind"], spec["nodes"], spec.get("corners", "round"),
                        spec.get("edges", []), reference_style, spec.get("layout", "legacy"),
                        float(style["ref_size"]))
    by_id = {node["id"]: node for node in nodes}
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 210 297" width="210mm" height="297mm" role="img">',
        '<title>' + escape(f"도 {spec['figure']} {spec['title']}") + '</title>',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L8,4 L0,8 Z" fill="#000"/></marker></defs>',
        '<rect x="0" y="0" width="210" height="297" fill="#fff"/>',
        f'<g fill="none" stroke="#000" stroke-width="{style["stroke_width"]}" stroke-linecap="round" stroke-linejoin="round">',
    ]
    if any(node.get("hatch") for node in nodes):
        parts.append('<defs><pattern id="blocked-hatch" patternUnits="userSpaceOnUse" width="3" height="3"><path d="M-1,1 L1,-1 M0,3 L3,0 M2,4 L4,2" fill="none" stroke="#000" stroke-width="0.35"/></pattern></defs>')
    for group in spec.get("groups", []):
        dash = ' stroke-dasharray="2 1.5"' if group.get("dashed", True) else ""
        parts.append(f'<rect class="system-group" x="{group["x"]:.2f}" y="{group["y"]:.2f}" width="{group["w"]:.2f}" height="{group["h"]:.2f}" fill="none"{dash}/>')
        parts.append(f'<text x="{group["x"]+group["w"]/2:.2f}" y="{group["y"]-2:.2f}" text-anchor="middle" fill="#000" stroke="none" font-family="{FONT_FAMILY}" font-size="3.8" font-weight="700">{escape(group["label"])} ({escape(str(group["ref"]))})</text>')
    for edge in spec.get("edges", []):
        source, target = by_id[edge["from"]], by_id[edge["to"]]
        via = edge.get("via", [])
        if via:
            first = {"x": via[0][0], "y": via[0][1], "w": 0, "h": 0}
            last = {"x": via[-1][0], "y": via[-1][1], "w": 0, "h": 0}
            points = [boundary(source, first), *(tuple(point) for point in via), boundary(target, last)]
        else:
            points = [boundary(source, target), boundary(target, source)]
        x1, y1 = points[0]; x2, y2 = points[-1]
        edge_style = edge.get("style", "dashed" if edge.get("dashed") else "solid")
        dash = f' stroke-dasharray="{style["edge_dash"]}"' if edge_style == "dashed" else ' stroke-dasharray="0.5 1.8"' if edge_style == "dotted" else ""
        arrow = edge.get("arrow", edge_style != "blocked")
        marker = ' marker-end="url(#arrow)"' if arrow else ""
        if via:
            coordinates = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
            parts.append(f'<polyline points="{coordinates}" fill="none"{marker}{dash}/>')
        else:
            parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"{marker}{dash}/>')
        if edge_style == "blocked":
            mx, my = path_midpoint(points)
            parts.append(f'<path d="M{mx-2:.2f},{my-2:.2f} L{mx+2:.2f},{my+2:.2f} M{mx-2:.2f},{my+2:.2f} L{mx+2:.2f},{my-2:.2f}" stroke-width="0.9"/>')
        label = edge.get("label")
        if label:
            mx, my = path_midpoint(points); my -= 2
            width = min(42, max(12, len(str(label)) * 3.2))
            parts.append(f'<rect x="{mx-width/2:.2f}" y="{my-4:.2f}" width="{width:.2f}" height="6" fill="#fff" stroke="none"/>')
            parts.append(f'<text x="{mx:.2f}" y="{my:.2f}" text-anchor="middle" fill="#000" stroke="none" font-family="{FONT_FAMILY}" font-size="3.2">{escape(str(label))}</text>')
    for node in nodes:
        shape = node["shape"]
        node_dash = ' stroke-dasharray="1.5 1.2"' if node.get("optional") else ""
        fill = 'url(#blocked-hatch)' if node.get("hatch") else '#fff'
        if shape == "ellipse":
            parts.append(f'<ellipse cx="{node["x"]+node["w"]/2:.2f}" cy="{node["y"]+node["h"]/2:.2f}" rx="{node["w"]/2:.2f}" ry="{node["h"]/2:.2f}" fill="{fill}"{node_dash}/>')
        else:
            radius = 3 if shape == "round" else 0
            parts.append(f'<rect x="{node["x"]:.2f}" y="{node["y"]:.2f}" width="{node["w"]:.2f}" height="{node["h"]:.2f}" rx="{radius}" fill="{fill}"{node_dash}/>')
        cx, cy = node["x"] + node["w"] / 2, node["y"] + node["h"] / 2
        label_lines = node["label"].split("\n")
        if node.get("subparts"):
            if not node.get("show_ref", True):
                label_lines[0] += f" ({node['ref']})"
            label_lines.extend(f"{part['label']} ({part['ref']})" for part in node["subparts"])
        for index, line in enumerate(label_lines):
            text_y = cy + 1 + (index - (len(label_lines) - 1) / 2) * 4.7
            if node.get("hatch"):
                text_width = min(node["w"] - 3, max(12, len(line) * float(style["label_size"]) * 0.7))
                parts.append(f'<rect x="{cx-text_width/2:.2f}" y="{text_y-3.3:.2f}" width="{text_width:.2f}" height="4.2" fill="#fff" stroke="none"/>')
            parts.append(f'<text x="{cx:.2f}" y="{text_y:.2f}" text-anchor="middle" fill="#000" stroke="none" font-family="{FONT_FAMILY}" font-size="{style["label_size"]}">{escape(line)}</text>')
        if not node.get("show_ref", True):
            continue
        if reference_style == "leader":
            label_x = node["x"] + node["w"] - 6
            line_start_x = node["x"] + node["w"] - 4
            if shape == "ellipse":
                line_end_x = node["x"] + node["w"] * 0.85
                line_end_y = node["y"] + node["h"] * 0.15
            else:
                line_end_x = node["x"] + node["w"] - 2
                line_end_y = node["y"]
            parts.append(f'<line class="reference-leader" x1="{line_start_x:.2f}" y1="{node["y"]-4:.2f}" x2="{line_end_x:.2f}" y2="{line_end_y:.2f}" stroke="#000" stroke-width="0.5"/>')
            parts.append(f'<text class="reference-number" x="{label_x:.2f}" y="{node["y"]-5:.2f}" text-anchor="end" fill="#000" stroke="none" font-family="{FONT_FAMILY}" font-size="{style["ref_size"]}">{escape(str(node["ref"]))}</text>')
        else:
            parts.append(f'<text class="reference-number" x="{node["x"]+node["w"]-2:.2f}" y="{node["y"]+5:.2f}" text-anchor="end" fill="#000" stroke="none" font-family="{FONT_FAMILY}" font-size="{style["ref_size"]}">{escape(str(node["ref"]))}</text>')
    parts.append('</g>')
    parts.append(f'<text x="105" y="12" text-anchor="middle" fill="#000" font-family="{FONT_FAMILY}" font-size="5" font-weight="700">{escape(f"【도 {spec['figure']}】 {spec['title']}")}</text>')
    parts.append('<line x1="15" y1="246" x2="195" y2="246" stroke="#000" stroke-width="0.5"/>')
    parts.append(f'<text x="15" y="253" fill="#000" font-family="{FONT_FAMILY}" font-size="3.8" font-weight="700">부호의 설명</text>')
    legend = [(str(node["ref"]), node["label"].replace("\n", " ") + (" (선택적)" if node.get("optional") else "")) for node in nodes]
    legend.extend((str(part["ref"]), part["label"]) for node in nodes for part in node.get("subparts", []))
    legend.extend((str(group["ref"]), group["label"]) for group in spec.get("groups", []))
    for index, (ref, label) in enumerate(sorted(legend, key=lambda item: int(item[0]))):
        column, row = index % 2, index // 2
        x, y = 15 + column * 90, 260 + row * 6
        if y > 290:
            raise ValueError("symbol legend exceeds page; split the figure")
        parts.append(f'<text x="{x}" y="{y}" fill="#000" font-family="{FONT_FAMILY}" font-size="3.4">{escape(ref)}: {escape(label)}</text>')
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
