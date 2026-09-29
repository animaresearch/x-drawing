#!/usr/bin/env python3
"""End-to-end smoke tests for X-Drawing."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent


def test_optional_component_and_presets() -> None:
    spec = {
        "figure": 2,
        "title": "장치 구성도",
        "kind": "system",
        "corners": "square",
        "style": "compact",
        "reference_style": "leader",
        "nodes": [
            {"id": "sensor", "label": "센서부", "ref": "100"},
            {"id": "alarm", "label": "경보부", "ref": "200", "optional": True},
        ],
        "edges": [{"from": "sensor", "to": "alarm"}],
    }
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / "figure.json"
        output = Path(temp) / "figure.svg"

        def run_render() -> subprocess.CompletedProcess[str]:
            source.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(ROOT / "render_patent_svg.py"), str(source), str(output)],
                capture_output=True, text=True, encoding="utf-8",
            )

        missing_source = run_render()
        assert missing_source.returncode == 2
        assert "source note" in missing_source.stderr

        spec["nodes"][1]["source"] = "발명자료의 선택적 경보 실시예; 청구항 3"
        rendered = run_render()
        assert rendered.returncode == 0, rendered.stderr
        svg = output.read_text(encoding="utf-8")
        root = ET.fromstring(svg)
        ns = {"svg": "http://www.w3.org/2000/svg"}
        nodes = [rect for rect in root.findall(".//svg:rect", ns) if rect.get("rx") is not None]
        assert len(nodes) == 2
        assert all(rect.get("rx") == "0" for rect in nodes)
        assert sum(bool(rect.get("stroke-dasharray")) for rect in nodes) == 1
        assert "(선택적)" in svg
        assert spec["nodes"][1]["source"] not in svg
        assert 'font-size="3.6"' in svg

        audit = subprocess.run(
            [sys.executable, str(ROOT / "audit_patent_svg.py"), str(output)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert audit.returncode == 0, audit.stdout + audit.stderr
        assert "dashed component found" in audit.stdout

        spec["style"] = "neon"
        assert run_render().returncode == 2
        spec["style"] = "default"
        spec["nodes"][1]["optional"] = "yes"
        assert run_render().returncode == 2


def test_leaders_and_connected_layout() -> None:
    spec = {
        "figure": 3,
        "title": "처리 흐름",
        "kind": "system",
        "corners": "square",
        "layout": "directed",
        "reference_style": "leader",
        "nodes": [
            {"id": "last", "label": "출력부", "ref": "300"},
            {"id": "first", "label": "입력부", "ref": "100"},
            {"id": "middle", "label": "처리부", "ref": "200"},
        ],
        "edges": [{"from": "first", "to": "middle"}, {"from": "middle", "to": "last"}],
    }
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / "figure.json"
        output = Path(temp) / "figure.svg"

        def run_render() -> subprocess.CompletedProcess[str]:
            source.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(ROOT / "render_patent_svg.py"), str(source), str(output)],
                capture_output=True, text=True, encoding="utf-8",
            )

        assert run_render().returncode == 0
        root = ET.parse(output).getroot()
        ns = {"svg": "http://www.w3.org/2000/svg"}
        boxes = [rect for rect in root.findall(".//svg:rect", ns) if rect.get("rx") is not None]
        assert len(boxes) == 3
        assert float(boxes[1].get("y")) < float(boxes[2].get("y")) < float(boxes[0].get("y"))
        leaders = [line for line in root.findall(".//svg:line", ns) if line.get("class") == "reference-leader"]
        assert len(leaders) == 3
        for box, leader in zip(boxes, leaders):
            assert float(leader.get("x1")) > float(box.get("x")) + float(box.get("width")) / 2
            assert float(leader.get("y2")) == float(box.get("y"))

        spec["reference_style"] = "inside"
        assert run_render().returncode == 0
        assert 'class="reference-leader"' not in output.read_text(encoding="utf-8")

        spec["reference_style"] = "leader"
        spec["kind"] = "flow"
        spec["nodes"] = [
            {"id": f"step{i}", "label": f"단계{i}", "ref": str(100 + i)}
            for i in range(8)
        ]
        spec["edges"] = []
        crowded = run_render()
        assert crowded.returncode == 2
        assert "reference leader" in crowded.stderr

        spec["kind"] = "system"
        spec["nodes"] = [{"id": "top", "label": "상단", "ref": "100", "x": 50, "y": 20}]
        too_high = run_render()
        assert too_high.returncode == 2
        assert "figure heading" in too_high.stderr


def test_legacy_and_grid_layouts() -> None:
    spec = {
        "figure": 4,
        "title": "기존 배치",
        "kind": "system",
        "nodes": [
            {"id": "first", "label": "입력", "ref": "100"},
            {"id": "middle", "label": "처리", "ref": "200"},
            {"id": "last", "label": "출력", "ref": "300"},
        ],
        "edges": [{"from": "first", "to": "middle"}, {"from": "middle", "to": "last"}],
    }
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / "figure.json"
        output = Path(temp) / "figure.svg"

        def run_render() -> subprocess.CompletedProcess[str]:
            source.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(ROOT / "render_patent_svg.py"), str(source), str(output)],
                capture_output=True, text=True, encoding="utf-8",
            )

        assert run_render().returncode == 0
        root = ET.parse(output).getroot()
        ns = {"svg": "http://www.w3.org/2000/svg"}
        boxes = [rect for rect in root.findall(".//svg:rect", ns) if rect.get("rx") is not None]
        assert float(boxes[0].get("y")) == float(boxes[1].get("y"))
        assert float(boxes[2].get("y")) > float(boxes[1].get("y"))
        assert 'class="reference-leader"' not in output.read_text(encoding="utf-8")

        spec["kind"] = "state"
        spec["reference_style"] = "leader"
        spec["nodes"].append({"id": "fourth", "label": "대기", "ref": "400"})
        assert run_render().returncode == 0
        assert output.read_text(encoding="utf-8").count('class="reference-leader"') == 4


def test_group_hatch_and_routed_paths() -> None:
    spec = {
        "figure": 5,
        "title": "차단 및 진단 경로",
        "kind": "system",
        "groups": [{"ref": "100", "label": "실행 제어 시스템", "x": 60, "y": 35, "w": 130, "h": 160, "dashed": True}],
        "nodes": [
            {"id": "gate", "label": "차단부", "ref": "200", "x": 95, "y": 65, "w": 55, "h": 23, "hatch": True},
            {"id": "device", "label": "현장 객체", "ref": "500", "x": 15, "y": 145, "w": 55, "h": 30,
             "show_ref": False, "subparts": [{"ref": "520", "label": "구동부"}, {"ref": "530", "label": "센서"}]},
        ],
        "edges": [
            {"from": "gate", "to": "device", "style": "blocked", "via": [[85, 110], [75, 125]]},
            {"from": "gate", "to": "device", "style": "dotted", "arrow": False},
        ],
    }
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / "figure.json"
        output = Path(temp) / "figure.svg"
        source.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        rendered = subprocess.run(
            [sys.executable, str(ROOT / "render_patent_svg.py"), str(source), str(output)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert rendered.returncode == 0, rendered.stderr
        svg = output.read_text(encoding="utf-8")
        assert 'class="system-group"' in svg
        assert 'id="blocked-hatch"' in svg
        assert 'stroke-dasharray="0.5 1.8"' in svg
        assert "<polyline" in svg
        assert "520: 구동부" in svg and "530: 센서" in svg
        assert "현장 객체 (500)" in svg
        audit = subprocess.run(
            [sys.executable, str(ROOT / "audit_patent_svg.py"), str(output)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert audit.returncode == 0, audit.stdout + audit.stderr
        assert "dashed component found" not in audit.stdout

        spec["groups"][0]["ref"] = "200"
        source.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        rejected = subprocess.run(
            [sys.executable, str(ROOT / "render_patent_svg.py"), str(source), str(output)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert rejected.returncode == 2


def main() -> int:
    spec = {
        "figure": 1,
        "title": "시스템 구성도",
        "kind": "system",
        "nodes": [
            {"id": "client", "label": "클라이언트", "ref": "100"},
            {"id": "control", "label": "제어부", "ref": "200"},
            {"id": "store", "label": "저장부", "ref": "300"},
        ],
        "edges": [
            {"from": "client", "to": "control", "label": "요청"},
            {"from": "control", "to": "store", "label": "기록"},
        ],
    }
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        source, output = directory / "figure.json", directory / "figure.svg"
        source.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        render = subprocess.run([sys.executable, str(ROOT / "render_patent_svg.py"), str(source), str(output)], capture_output=True, text=True, encoding="utf-8")
        assert render.returncode == 0, render.stderr
        ET.parse(output)
        audit = subprocess.run([sys.executable, str(ROOT / "audit_patent_svg.py"), str(output)], capture_output=True, text=True, encoding="utf-8")
        assert audit.returncode == 0, audit.stdout + audit.stderr
        assert "PASS" in audit.stdout
        duplicate = dict(spec)
        duplicate["nodes"] = [dict(node) for node in spec["nodes"]]
        duplicate["nodes"][1]["ref"] = "100"
        source.write_text(json.dumps(duplicate, ensure_ascii=False), encoding="utf-8")
        rejected = subprocess.run([sys.executable, str(ROOT / "render_patent_svg.py"), str(source), str(output)], capture_output=True, text=True, encoding="utf-8")
        assert rejected.returncode == 2
    test_optional_component_and_presets()
    test_leaders_and_connected_layout()
    test_legacy_and_grid_layouts()
    test_group_hatch_and_routed_paths()
    print("X-Drawing tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
