#!/usr/bin/env python3
"""Render a validated monochrome patent figure from JSON to standalone SVG."""

from __future__ import annotations

import argparse
from html import escape
import json
import math
from pathlib import Path
import sys


KINDS = {"system", "flow", "state", "sequence", "exploded"}
SHAPES = {"rect", "round", "ellipse"}
MAX_NODES = 20
PART_TYPES = {"cover", "frame", "board", "block", "tray"}
MAX_PARTS = 8
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
    if data["kind"] == "exploded":
        validate_exploded(data)
        return data
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


def _number(value: object, low: float, high: float, name: str) -> float:
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(value) or not low <= value <= high):
        raise ValueError(f"{name} must be numeric within {low}-{high}")
    return float(value)


def _positions(value: object, name: str, limit: int = 8) -> None:
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"{name} must be a list of up to {limit} positions")
    for index, point in enumerate(value):
        if not isinstance(point, dict) or set(point) != {"u", "v"}:
            raise ValueError(f"{name}[{index}] needs only u and v")
        _number(point["u"], 0.05, 0.95, f"{name}[{index}].u")
        _number(point["v"], 0.05, 0.95, f"{name}[{index}].v")


def validate_exploded(spec: dict) -> None:
    """Validate an explicit hardware stack without inferring unlisted details."""
    if any(key in spec for key in ("nodes", "edges", "groups")):
        raise ValueError("exploded figures use parts, not nodes, edges, or groups")
    if spec.get("projection", "dimetric") != "dimetric":
        raise ValueError("exploded projection must be dimetric")
    if spec.get("reference_style", "leader") != "leader":
        raise ValueError("exploded reference_style must be leader")
    if spec.get("style", "default") not in STYLE_PRESETS:
        raise ValueError("style must be default or compact")
    stack = spec.get("stack", {})
    if not isinstance(stack, dict) or set(stack) - {"cx", "gap", "guides"}:
        raise ValueError("stack accepts only cx, gap, and guides")
    _number(stack.get("cx", 100), 60, 140, "stack.cx")
    _number(stack.get("gap", 8), 2, 25, "stack.gap")
    if not isinstance(stack.get("guides", True), bool):
        raise ValueError("stack.guides must be boolean")
    parts = spec.get("parts")
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_PARTS:
        raise ValueError(f"parts must contain 1-{MAX_PARTS} objects")
    ids: set[str] = set()
    refs: set[str] = set()
    common = {"id", "type", "ref", "label", "width", "depth", "thickness"}
    detail_fields = {
        "cover": {"vents", "holes"},
        "frame": {"wall", "gasket"},
        "board": {"chips", "holes", "traces"},
        "block": {"poles", "terminals"},
        "tray": {"inset", "holes"},
    }
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ValueError(f"part {index} must be an object")
        part_id, kind, ref = part.get("id"), part.get("type"), str(part.get("ref", ""))
        if not isinstance(part_id, str) or not part_id.strip() or part_id in ids:
            raise ValueError(f"part {index} has a missing or duplicate id")
        if not isinstance(kind, str) or kind not in PART_TYPES:
            raise ValueError(f"part {part_id} has an unsupported type")
        if set(part) - common - detail_fields[kind]:
            raise ValueError(f"part {part_id} has unsupported fields for type {kind}")
        if not isinstance(part.get("label"), str) or not part["label"].strip():
            raise ValueError(f"part {part_id} needs a label")
        if not ref.isdigit() or ref in refs:
            raise ValueError(f"part {part_id} needs a unique numeric ref")
        ids.add(part_id)
        refs.add(ref)
        _number(part.get("width"), 20, 100, f"part {part_id} width")
        _number(part.get("depth"), 15, 70, f"part {part_id} depth")
        _number(part.get("thickness"), 0.5, 25, f"part {part_id} thickness")
        if "holes" in part:
            _positions(part["holes"], f"part {part_id} holes")
        if kind == "cover":
            vents = part.get("vents", 0)
            if not isinstance(vents, int) or isinstance(vents, bool) or not 0 <= vents <= 8:
                raise ValueError(f"part {part_id} vents must be an integer within 0-8")
        elif kind == "frame":
            _number(part.get("wall", 0.1), 0.04, 0.25, f"part {part_id} wall")
            if not isinstance(part.get("gasket", False), bool):
                raise ValueError(f"part {part_id} gasket must be boolean")
        elif kind == "board":
            traces = part.get("traces", 0)
            if not isinstance(traces, int) or isinstance(traces, bool) or not 0 <= traces <= 6:
                raise ValueError(f"part {part_id} traces must be an integer within 0-6")
            chips = part.get("chips", [])
            if not isinstance(chips, list) or len(chips) > 4:
                raise ValueError(f"part {part_id} chips must be a list of up to four chips")
            for chip_index, chip in enumerate(chips):
                if not isinstance(chip, dict) or set(chip) - {"u", "v", "w", "d", "h"}:
                    raise ValueError(f"part {part_id} chip {chip_index} has unsupported fields")
                for field, low, high in (("u", 0.1, 0.9), ("v", 0.1, 0.9),
                                         ("w", 0.05, 0.4), ("d", 0.05, 0.4), ("h", 0.5, 8)):
                    _number(chip.get(field), low, high, f"part {part_id} chip {chip_index} {field}")
                if (chip["u"] - chip["w"] / 2 < 0.05 or chip["u"] + chip["w"] / 2 > 0.95
                        or chip["v"] - chip["d"] / 2 < 0.05 or chip["v"] + chip["d"] / 2 > 0.95):
                    raise ValueError(f"part {part_id} chip {chip_index} extends outside the board")
                if index > 0 and chip["h"] > stack.get("gap", 8):
                    raise ValueError(f"part {part_id} chip {chip_index} is taller than the gap above the board")
        elif kind == "block":
            poles = part.get("poles", [])
            if not isinstance(poles, list) or len(poles) > 2:
                raise ValueError(f"part {part_id} poles must be a list of up to two poles")
            for pole in poles:
                if not isinstance(pole, dict) or set(pole) != {"u", "sign"}:
                    raise ValueError(f"part {part_id} pole needs u and sign")
                _number(pole["u"], 0.1, 0.9, f"part {part_id} pole u")
                if not isinstance(pole["sign"], str) or pole["sign"] not in {"+", "-"}:
                    raise ValueError(f"part {part_id} pole sign must be + or -")
            if not isinstance(part.get("terminals", False), bool):
                raise ValueError(f"part {part_id} terminals must be boolean")
        elif kind == "tray":
            _number(part.get("inset", 0.1), 0.04, 0.25, f"part {part_id} inset")


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
    if spec["kind"] == "exploded":
        return render_exploded(spec)
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


def _face(cx: float, cy: float, width: float, depth: float) -> list[tuple[float, float]]:
    """Projected top plane, ordered left, back, right, front."""
    ux, uy = width * 0.75, width * 0.28
    vx, vy = depth * 0.75, -depth * 0.28
    left = (cx - (ux + vx) / 2, cy - (uy + vy) / 2)
    back = (left[0] + vx, left[1] + vy)
    right = (back[0] + ux, back[1] + uy)
    front = (left[0] + ux, left[1] + uy)
    return [left, back, right, front]


def _top_uv(face: list[tuple[float, float]], u: float, v: float) -> tuple[float, float]:
    left, back, _, front = face
    return (left[0] + u * (front[0] - left[0]) + v * (back[0] - left[0]),
            left[1] + u * (front[1] - left[1]) + v * (back[1] - left[1]))


def _points(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _polygon(points: list[tuple[float, float]], fill: str = "#fff") -> str:
    return f'<polygon points="{_points(points)}" fill="{fill}"/>'


def _slab(cx: float, cy: float, width: float, depth: float, thickness: float,
          draw_top: bool = True) -> tuple[list[str], list[tuple[float, float]]]:
    face = _face(cx, cy, width, depth)
    left, _, right, front = face
    down = lambda point: (point[0], point[1] + thickness)
    result = [
        _polygon([left, front, down(front), down(left)]),
        _polygon([front, right, down(right), down(front)]),
    ]
    if draw_top:
        result.append(_polygon(face))
    return result, face


def _inner_face(face: list[tuple[float, float]], margin: float) -> list[tuple[float, float]]:
    return [_top_uv(face, margin, margin), _top_uv(face, margin, 1 - margin),
            _top_uv(face, 1 - margin, 1 - margin), _top_uv(face, 1 - margin, margin)]


def _exploded_layout(spec: dict) -> list[dict]:
    parts = [dict(part) for part in spec["parts"]]
    stack = spec.get("stack", {})
    gap = float(stack.get("gap", 8))
    cx = float(stack.get("cx", 100))
    for part in parts:
        part["_face_height"] = 0.28 * (part["width"] + part["depth"])
        part["_height"] = part["_face_height"] + part["thickness"]
    total_height = sum(part["_height"] for part in parts) + gap * (len(parts) - 1)
    band_top, band_bottom = 25.0, 235.0
    if total_height > band_bottom - band_top:
        raise ValueError("exploded stack is too tall; reduce part size, thickness, gap, or count")
    cursor = band_top + (band_bottom - band_top - total_height) / 2
    for part in parts:
        part["_cx"] = cx
        part["_cy"] = cursor + part["_face_height"] / 2
        part["_face"] = _face(cx, part["_cy"], part["width"], part["depth"])
        left = min(point[0] for point in part["_face"])
        right = max(point[0] for point in part["_face"])
        if left < 14 or right > 165:
            raise ValueError(f"part {part['id']} exceeds horizontal drawing area")
        cursor += part["_height"] + gap
    return parts


def render_exploded(spec: dict) -> str:
    """Render a structured single-stack exploded diagram on the filing-sized page."""
    parts = _exploded_layout(spec)
    style = STYLE_PRESETS[spec.get("style", "default")]
    result = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 210 297" width="210mm" height="297mm" role="img">',
        '<title>' + escape(f"도 {spec['figure']} {spec['title']}") + '</title>',
        '<rect x="0" y="0" width="210" height="297" fill="#fff"/>',
        f'<g fill="none" stroke="#000" stroke-width="{style["stroke_width"]}" stroke-linecap="round" stroke-linejoin="round">',
    ]
    if spec.get("stack", {}).get("guides", True) and len(parts) > 1:
        widest = max(parts, key=lambda part: max(p[0] for p in part["_face"]) - min(p[0] for p in part["_face"]))
        guide_xs = sorted({round(point[0], 2) for point in widest["_face"]})
        for x in guide_xs:
            aligned = [part for part in parts if min(p[0] for p in part["_face"]) - 0.01 <= x <= max(p[0] for p in part["_face"]) + 0.01]
            if len(aligned) < 2:
                continue
            y_start = max(point[1] for point in aligned[0]["_face"]) + aligned[0]["thickness"]
            y_end = aligned[-1]["_cy"]
            result.append(f'<line class="exploded-guide" x1="{x:.2f}" y1="{y_start:.2f}" x2="{x:.2f}" y2="{y_end:.2f}" stroke-width="0.35" stroke-dasharray="2 2"/>')

    for part in parts:
        face = part["_face"]
        cx, cy = part["_cx"], part["_cy"]
        width, depth, thickness = part["width"], part["depth"], part["thickness"]
        kind = part["type"]
        if kind == "frame":
            sides, _ = _slab(cx, cy, width, depth, thickness, draw_top=False)
            result.extend(sides)
            inner = _inner_face(face, float(part.get("wall", 0.1)))
            outer_path = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in face) + " Z"
            inner_path = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in inner) + " Z"
            result.append(f'<path d="{outer_path} {inner_path}" fill="#fff" fill-rule="evenodd"/>')
            if part.get("gasket"):
                second = _inner_face(face, min(0.46, float(part.get("wall", 0.1)) + 0.04))
                result.append(_polygon(second, fill="none"))
        else:
            slab, _ = _slab(cx, cy, width, depth, thickness)
            result.extend(slab)
            if kind == "tray":
                inner = _inner_face(face, float(part.get("inset", 0.1)))
                result.append(_polygon(inner, fill="none"))
        for hole in part.get("holes", []):
            x, y = _top_uv(face, hole["u"], hole["v"])
            result.append(f'<ellipse cx="{x:.2f}" cy="{y:.2f}" rx="1.25" ry="0.55" fill="#fff" stroke-width="0.4"/>')
        if kind == "cover":
            for index in range(part.get("vents", 0)):
                u = 0.5 if part["vents"] == 1 else 0.34 + index * 0.32 / (part["vents"] - 1)
                a = _top_uv(face, u, 0.32); b = _top_uv(face, u, 0.65)
                result.append(f'<line x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}" stroke-width="0.45"/>')
        elif kind == "board":
            for index in range(part.get("traces", 0)):
                u = 0.12 + index * 0.045
                a = _top_uv(face, u, 0.1); b = _top_uv(face, u, 0.72)
                result.append(f'<line x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}" stroke-width="0.3"/>')
            for chip in part.get("chips", []):
                chip_x, chip_y = _top_uv(face, chip["u"], chip["v"])
                chip_shape, _ = _slab(chip_x, chip_y - chip["h"], width * chip["w"],
                                      depth * chip["d"], chip["h"])
                result.extend(chip_shape)
        elif kind == "block":
            if len(part.get("poles", [])) == 2:
                a = _top_uv(face, 0.5, 0); b = _top_uv(face, 0.5, 1)
                result.append(f'<line x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}" stroke-width="0.4"/>')
            for pole in part.get("poles", []):
                x, y = _top_uv(face, pole["u"], 0.5)
                if part.get("terminals"):
                    result.append(f'<ellipse cx="{x:.2f}" cy="{y:.2f}" rx="1.2" ry="0.55" fill="#fff" stroke-width="0.35"/>')
                result.append(f'<text x="{x:.2f}" y="{y-1:.2f}" text-anchor="middle" fill="#000" stroke="none" font-family="Arial, sans-serif" font-size="4">{pole["sign"]}</text>')

    for part in parts:
        right_corner = part["_face"][2]
        label_y = part["_cy"] + 1.2
        result.append(f'<path d="M{right_corner[0]:.2f},{right_corner[1]:.2f} Q{(right_corner[0]+178)/2:.2f},{label_y-3:.2f} 178,{label_y:.2f}" fill="none" stroke-width="0.35"/>')
        result.append(f'<text x="181" y="{label_y+1:.2f}" fill="#000" stroke="none" font-family="{FONT_FAMILY}" font-size="3.8">{escape(str(part["ref"]))}</text>')
    result.append('</g>')
    result.append(f'<text x="105" y="12" text-anchor="middle" fill="#000" font-family="{FONT_FAMILY}" font-size="5" font-weight="700">{escape(f"【도 {spec['figure']}】 {spec['title']}")}</text>')
    result.append('<line x1="15" y1="246" x2="195" y2="246" stroke="#000" stroke-width="0.5"/>')
    result.append(f'<text x="15" y="253" fill="#000" font-family="{FONT_FAMILY}" font-size="3.8" font-weight="700">부호의 설명</text>')
    legend = [(str(part["ref"]), part["label"]) for part in parts]
    for index, (ref, label) in enumerate(sorted(legend, key=lambda item: int(item[0]))):
        col, row = index % 2, index // 2
        x, y = 15 + col * 90, 260 + row * 6
        if y > 290:
            raise ValueError("exploded symbol legend exceeds page; split the figure")
        result.append(f'<text x="{x}" y="{y}" fill="#000" font-family="{FONT_FAMILY}" font-size="3.4">{escape(ref)}: {escape(label)}</text>')
    result.append('</svg>')
    return "\n".join(result) + "\n"


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
