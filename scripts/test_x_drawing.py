#!/usr/bin/env python3
"""End-to-end smoke tests for X-Drawing."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent


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
    print("X-Drawing tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
