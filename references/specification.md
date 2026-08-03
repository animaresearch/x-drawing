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

When geometry is omitted, the renderer applies a simple deterministic layout. For crowded or
crossing-heavy figures, set coordinates explicitly and rerun the audit.

## Reference numerals

Reserve stable ranges by subsystem when useful, such as 100-series for clients, 200-series for
control components, and 300-series for storage. Do not change an element's numeral between
figures. The same numeral must always denote the same named element.
