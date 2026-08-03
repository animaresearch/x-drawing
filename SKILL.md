---
name: x-drawing
description: Generate and audit filing-oriented monochrome patent drawings as self-contained SVG from invention descriptions or structured JSON. Use when the user asks for X-도면, patent figures, system/block diagrams, process flows, state diagrams, reference numerals, symbol legends, or black-and-white technical drawings for a patent draft.
---

# X-Drawing

Create restrained black-and-white patent figures. Do not generate presentation graphics.

## Workflow

1. Read the invention description and identify only elements supported by it.
2. Propose the smallest useful figure set. Prefer:
   - system/block diagram for components and boundaries;
   - flow diagram for method steps;
   - state diagram for transitions;
   - sequence diagram only when call order is essential.
3. Assign stable reference numerals. Reuse the same numeral for the same element across figures.
4. Create one JSON file per figure using [references/specification.md](references/specification.md).
5. Render with `scripts/render_patent_svg.py`.
6. Run `scripts/audit_patent_svg.py` on every SVG and fix all errors.
7. Compare every label and numeral against the source description. Flag invented structure instead of silently adding it.

## Commands

```powershell
python scripts/render_patent_svg.py figure.json figure.svg
python scripts/audit_patent_svg.py figure.svg
```

## Drawing rules

- Use black strokes, white fill, and no decorative colour, gradient, shadow, icon, or texture.
- Use SVG `viewBox="0 0 210 297"` and system sans-serif fonts; require no network access.
- Keep labels short and concrete. Put detailed explanation in the specification, not the drawing.
- Use visible arrowheads and avoid line crossings. Prefer orthogonal conceptual flow.
- Show reference numerals beside their elements and include a symbol legend.
- Keep the figure number and short title separate from the technical labels.
- Preserve SVG as the canonical source. Convert to a filing image only after visual inspection.
- Do not claim jurisdictional compliance automatically; filing-office requirements and attorney review control.

## Quality gate

Require all of the following:

- unique node IDs and consistent reference numerals;
- no missing edge endpoints;
- no clipped nodes or legend entries;
- monochrome palette only;
- no external URL, script, font, or embedded raster image;
- readable labels at print scale;
- one-to-one agreement between the drawing, symbol legend, and specification terminology.

The skill is a drawing aid, not a legal opinion. Do not infer undisclosed embodiments.
