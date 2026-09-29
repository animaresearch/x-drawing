# X-Drawing Figure Specification

Use one JSON object per figure:

```json
{
  "figure": 1,
  "title": "시스템 구성도",
  "kind": "system",
  "nodes": [
    {"id": "client", "label": "클라이언트", "ref": "100"},
    {"id": "controller", "label": "제어부", "ref": "200"}
  ],
  "edges": [
    {"from": "client", "to": "controller", "label": "요청"}
  ]
}
```

## Fields

- `figure`: positive integer.
- `title`: concise figure title.
- `kind`: `system`, `flow`, `state`, or `sequence`.
- `nodes`: 1-20 objects with unique `id`, non-empty `label`, and unique numeric `ref`.
- `edges`: objects with valid `from` and `to`; optional `label` and `dashed` boolean.
- Optional node geometry: `x`, `y`, `w`, `h` in the 210x297 coordinate system.
- Optional node `shape`: `rect`, `round`, or `ellipse`.
- Optional figure `corners`: `round` (default) or `square`. This sets the shape of nodes without their own `shape`.
- Optional figure `style`: `default` (default) or `compact`. These are built-in monochrome presets; `compact` needs a print-size visual check.
- Optional figure `reference_style`: `inside` (default) preserves existing figures; `leader` places numerals outside boxes with short leader lines.
- Optional figure `layout`: `legacy` (default) preserves the original grid/flow placement; `directed` centers flows and orders simple 3-6-node system chains by their edges.
- Optional node `optional`: boolean, default `false`. `true` draws a dashed border and adds `(선택적)` to the symbol legend.
- Every node with `optional: true` needs a non-empty `source` note identifying where the optional embodiment appears in the invention materials or draft claims. This note stays in JSON and is not drawn in the SVG. The renderer checks its presence, not whether the cited material actually supports the designation.
- Optional node `hatch: true` draws black diagonal hatching. Use it only for a component explicitly marked blocked in the source materials.
- Optional node `subparts` is a list of `{"ref": "520", "label": "하부 구동부"}` objects. Each subpart appears as a line inside its parent node and in the symbol legend. Their reference numerals must be unique across all nodes, subparts, and groups.
- Optional node `show_ref: false` hides the external/in-corner numeral. Use it for a parent box that displays its own numeral with subparts inside; the legend still includes the parent.
- Optional `groups` is a list of `{"ref": "100", "label": "실행 제어 시스템", "x": 60, "y": 35, "w": 130, "h": 160, "dashed": true}` objects. A group is drawn behind nodes as a labelled boundary and appears in the symbol legend. Its geometry uses the same 210×297 coordinates; groups may contain nodes.
- Optional edge `style` is `solid` (default), `dashed`, `dotted`, or `blocked`. The legacy `dashed` boolean remains supported. `blocked` draws an X on the connection and omits the arrowhead unless `arrow: true` is set.
- Optional edge `via` is a list of up to eight `[x, y]` points for an orthogonal or deliberately routed connection. The renderer connects the source and target borders through these points; inspect the result for line crossings. Optional `arrow` controls the arrowhead.

An omitted `optional` field means **unclassified**, not legally required. A solid border is the
default visual style and does not itself assert claim scope. Use dashed borders only when the
source materials support that specific visual convention; an examiner or filing office may expect
different conventions. Do not infer optional status from the figure layout.

For example:

```json
{
  "figure": 2,
  "title": "장치 구성도",
  "kind": "system",
  "corners": "square",
  "style": "default",
  "layout": "directed",
  "reference_style": "leader",
  "nodes": [
    {"id": "sensor", "label": "센서부", "ref": "100"},
    {"id": "alarm", "label": "경보부", "ref": "200", "optional": true, "source": "발명자료의 선택적 경보 실시예; 청구항 3"}
  ],
  "edges": [{"from": "sensor", "to": "alarm"}]
}
```

When geometry is omitted, the renderer applies a simple deterministic layout. For crowded or
crossing-heavy figures, set coordinates explicitly and rerun the audit. With `layout: "directed"`,
a `system` figure that forms one directed chain of 3-6 nodes is ordered vertically by its edges,
even if the JSON node list is in a different order. Flow figures are centered vertically in this
mode. Directed layout requires either all node coordinates or none; partial manual placement is
rejected. The renderer rejects node overlaps and leader-number collisions; split dense figures
or supply suitable geometry.

## Reference numerals

Reserve stable ranges by subsystem when useful, such as 100-series for clients, 200-series for
control components, and 300-series for storage. Do not change an element's numeral between
figures. The same numeral must always denote the same named element.

## Source and claim review

Before rendering, compare the invention description and draft claims with the proposed figure
set. Record which figure contains each claimed component or step, and flag claims that have no
corresponding figure where a figure is needed. Check every label, reference numeral, optional
designation, and omitted element against the source materials. This is a manual drafting review;
the renderer and SVG auditor cannot verify claim coverage or disclosure support.
