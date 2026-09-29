---
name: x-drawing
description: Generate and audit filing-oriented monochrome patent drawings as self-contained SVG from invention descriptions or structured JSON. Use when the user asks for X-도면, patent figures, system/block diagrams, process flows, state diagrams, hardware exploded views, reference numerals, symbol legends, or black-and-white technical drawings for a patent draft.
---

# X-Drawing

Create restrained black-and-white patent figures. Do not generate presentation graphics.

## Workflow

1. Read the invention description and drafted claims when supplied. Identify only elements supported by the materials.
2. Propose the smallest useful figure set. Prefer:
   - system/block diagram for components and boundaries;
   - flow diagram for method steps;
   - state diagram for transitions;
   - sequence diagram only when call order is essential;
   - exploded diagram when a disclosed physical assembly needs its parts shown apart.
3. Assign stable reference numerals. Reuse the same numeral for the same element across figures.
4. Map claimed components and steps to the proposed figures. Flag a claim with no useful figure, an unsupported figure element, or a change of terminology. Create one JSON file per figure using [references/specification.md](references/specification.md).
5. Render with `scripts/render_patent_svg.py`.
6. Run `scripts/audit_patent_svg.py` on every SVG and fix all errors.
7. Compare every label and numeral against the source description. Flag invented structure instead of silently adding it.

## Commands

```powershell
python scripts/render_patent_svg.py figure.json figure.svg
python scripts/audit_patent_svg.py figure.svg
```

## Drawing rules

- Use black strokes and white fill with no decorative colour, gradient, shadow, icon, or texture. Use monochrome hatching only when it marks a blocked component or path in the source drawing.
- Preserve disclosed system boundaries, blocked paths, read-only diagnostic paths, and subordinate reference numerals when they matter to the figure. Use `groups`, node `hatch`/`subparts`, and edge `style`/`via` as documented in [references/specification.md](references/specification.md).
- For `kind: "exploded"`, use an explicit top-to-bottom `parts` list and only the stated holes, vents, chips, traces, poles, and inset. Check the generated projection and leaders at print size. This schematic preset does not reproduce arbitrary mechanical geometry or a specific camera angle.
- Use `corners: "square"` for square boxes and a built-in `style` preset for a repeatable look. Keep the default appearance for existing figures.
- Set `optional: true` only for a source-supported optional component and provide that node's `source` note. It draws a dashed border and a legend annotation. A solid border by itself does not mean legally required.
- Use SVG `viewBox="0 0 210 297"` and system sans-serif fonts; require no network access.
- Keep labels short and concrete. Put detailed explanation in the specification, not the drawing.
- Use visible arrowheads and avoid line crossings. Prefer orthogonal conceptual flow.
- For new figures, select `reference_style: "leader"` to place reference numerals outside components with short leader lines, and include a symbol legend. The omitted field retains the prior in-box placement.
- For a simple connected system chain or process flow, select `layout: "directed"` to make connection order readable. The omitted field retains the prior automatic placement.
- Keep the figure number and short title separate from the technical labels.
- Preserve SVG as the canonical source. Convert to a filing image only after visual inspection.
- Do not claim jurisdictional compliance automatically; filing-office requirements and attorney review control.

## Quality gate

Require all of the following:

- unique node IDs and consistent reference numerals;
- no missing edge endpoints;
- no clipped nodes or legend entries;
- no overlapping nodes or reference-number leaders;
- monochrome palette only;
- no external URL, script, font, or embedded raster image;
- readable labels at print scale;
- one-to-one agreement between the drawing, symbol legend, and specification terminology.

The renderer checks that an optional node has a source note, but cannot validate the note's meaning. The SVG auditor cannot recover that source note from the drawing. Review both the JSON and source materials before using the figure.

The skill is a drawing aid, not a legal opinion. Do not infer undisclosed embodiments.
