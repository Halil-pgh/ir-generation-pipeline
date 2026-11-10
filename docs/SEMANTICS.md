# Semantics

Behaviour the schemas leave open is decided here, once, and every part of
the pipeline (front-end, checks, backends) follows it. When the spec and
this file disagree, this file wins until the spec is fixed.

## Issues

- A problem in a picture is an **issue**, never an exception. Its code
  (`E-SUBTITLE`) is defined once, in `ISSUE_CODES`, by the module that
  reports it. Reporting an unregistered code is a bug in that stage.
- The first letter of a code is its severity: `E-` error, `W-` warning.
  There are no other severities.
- Every code has an **origin**: `ir`, `capability`, `internal`,
  `environment` or `infeasible`. The origin belongs to the code, not to
  one issue, so an issue of a given code always goes to the same place.
- `path` is a JSON path into the IR written as `objects[3].size`;
  `objects` lists the ids involved, or a part of one such as `v.label`.

## Stopping a run

- A stage either writes every artifact it promised, or reports at least
  one error that says why it could not. In the second case the run stops
  after that stage, with status `STOPPED`.
- A stage that reports errors but still writes its outputs (a lint check)
  does not stop the run: the picture is still drawn, problems included.

## READY

A picture is `READY` when every stage ran and no issue is open: no
errors (an error can never be accepted), and every warning fixed or
accepted with an `allow` entry.
Otherwise it is `NOT_READY` (every stage ran) or `STOPPED` (one could not
go on). Allowed issues stay in the report, marked with their reason.

## `allow`

An entry `{"code", "objects", "reason"}` accepts issues on purpose.

- It matches an issue when the codes are equal and **every** object it
  names covers at least one object of the issue.
- An id covers itself and its parts: `v` covers `v` and `v.label`, but
  not `vx`. A group id covers everything inside it (from step 6 on, when
  groups exist).
- An entry with no objects matches only issues that name no objects,
  such as one about the picture as a whole. It is never a blanket pass
  for a whole code.
- Only codes defined as `allowable` can be accepted, and only warnings
  of origin `ir` can be allowable. An entry that names any other code is
  an `E-ALLOW` error and accepts nothing.
- The reason needs at least four words, so stock answers such as "ok"
  or "this is intended" do not pass. Each issue is accepted by the first
  entry that matches it.

## Canvas

- The short side of every frame is 9 units. The origin is at the center
  and y points up. At the reference size (short side 1080 px) one unit
  is 120 px.
- **Reference pixels** are pixels of the frame at that reference size.
  Margins, platform overlays, type sizes and stroke widths are given in
  reference pixels, so they mean the same at every output resolution.
- Pixel sizes are rounded up to the next even number, at the reference
  size and at the output size. The long side in units is the rounded
  reference long side divided by 120, so units and reference pixels
  always agree exactly. The output resolution changes how many pixels a
  unit is, never the units.
- Any `W:H` aspect between 1:4 and 4:1 is allowed; the presets are only
  names for common ones.
- Safe area = frame − margins − platform overlays − subtitle band. A
  platform that draws an interface over the picture accepts only the
  aspect its overlays were measured on.
- The subtitle band (modes `reserve` and `burn_in`) is
  lines × line spacing × caption size + one caption size of padding high.
  It runs between the side margins and overlays, and its bottom edge sits
  on the bottom margin plus the bottom overlay. The safe area ends at its
  top edge.

## IR document

- `ir.json` is one flat object: the header fields (`version`, `intent`,
  `frame`, `typography`, `colors`, `styles`) followed by the body fields
  (`focus`, `extra_colors`, `zones`, `spaces`, `defs`, `objects`,
  `allow`). The orchestrator owns the header and the agent owns the body;
  no field belongs to both.
- Every contract refuses unknown fields. A color has exactly two forms,
  `"#RRGGBB"` and `[r, g, b]`, never with alpha. A path is a start point
  plus segments; a named shape (`polygon`, `arc`…) is the way to say a
  common figure, and `path` is for everything else.
- Ids start with a letter and use letters, digits and `_`. A dot names a
  part of an object (`v.label`, `v.tip`), so ids never contain one.

## Paint

- Paint fields left out are inherited, in this order: theme defaults,
  then the object's style classes in the order listed (a later class
  wins), then the object's own fields.
- The theme defaults are the header's `theme`: texts take its `text`
  color, every other object its `line` color, every stroke its
  `stroke_width` (4 reference px when left out). A theme color left out
  is white or black, whichever has the higher WCAG contrast with the
  background. Nothing is filled; a text is `body` size, regular and
  upright.
- A color written directly on an object (`"#FFFFFF"`, `[255, 255, 255]`)
  is allowed, but reported as `W-UNDECLARED-COLOR`, since "one concept,
  one color" only holds while colors have names. Header colors, extra
  colors and `"none"` are names; colors in the header's style classes
  are the orchestrator's and are not reported.
- `"none"` as a color means no paint. It is reserved and cannot name a
  header color.
- `opacity` multiplies everything about the object. `fill_opacity`
  multiplies its fill as well. A group's opacity is multiplied into each
  child's, and is never applied to the group as one layer.
- Stroke widths, dashes and type sizes are in reference pixels; a size
  may also be a text role (`title`, `heading`, `body`, `label`,
  `caption`) from the header.

## Objects

- The basic shapes are `circle`, `ellipse`, `rect`, `regular_polygon`,
  `polygon` and `sector`, which are closed and may be filled, and
  `line`, `polyline` and `arc`, which are open and drawn as lines only
  (they have no `fill` field, and a style class's fill does not reach
  them). Any other figure is a `path`.
- Angles are degrees, counterclockwise from the positive x axis. An arc
  or sector runs from `start_angle` to `end_angle`: counterclockwise when
  `end_angle` is larger, clockwise when smaller. The sweep may not be 0
  and may not exceed 360.
- A `regular_polygon` with `rotation` 0 stands on a horizontal bottom
  edge: a triangle points up, a square is axis-aligned. `rotation` turns
  it counterclockwise about its center. `radius` is the distance from the
  center to each corner.
- `ellipse` and `rect` are axis-aligned; turn them with a group.
- Drawing order is list order; an object's `z` moves it, higher drawn
  later, and ties keep list order. `defs` are never drawn.
- A text's `anchor` names the point of its box that sits at `at`:
  horizontal part (`left`, `center`, `right`), then vertical part
  (`top`, `center`, `baseline`, `bottom`). `center` alone is both.
- A group's children are ids of other objects. Its transform is applied
  as: scale, then rotate (degrees, counterclockwise), both about `pivot`;
  then translate.

## LIR

- `lir.json` holds `version`, `canvas` (`units`, output `pixels`,
  `background`) and `items`. Every item is a group carrying the id of the
  IR object it draws; pieces a component makes get dotted ids
  (`axes.tick_3`). Group ids are unique in the whole document.
- Everything is resolved: colors are `"#RRGGBB"`, opacities are final
  (a group's opacity is already multiplied into its children, and clips
  are already cut), text boxes and baselines are measured. A backend
  never lays out, never resolves a name and never reorders.
- Drawing order is list order at every level. The front-end sorts by `z`
  before writing, so siblings' `z` never decreases; `z` stays in the file
  only so a reader can see why things are in that order.
- Positions are in units. A backend draws them at
  `pixels[i] / units[i]` pixels per unit. Stroke widths, dashes and type
  sizes are in reference pixels: multiply by `short side px / 1080`.
- A group's `transform` `[a, b, c, d, e, f]` maps (x, y) to
  (a x + c y + e, b x + d y + f), in units, applied to all its children.
- A path is drawn from its subpaths. Its `hint` names the IR shape it
  came from, with that shape's own numbers, so a backend may use its
  library's own class (Manim's `Circle`, `Arc`, `RegularPolygon`…); a
  backend that does not know a hint ignores it. The hint must describe
  the same geometry as the subpaths. A path always has a fill, a stroke
  or both.
- Curved shapes reach the LIR as cubic Bezier pieces of at most 90
  degrees each; a closed subpath's last side is its closing edge, not a
  segment.
- A text or math item is placed so that its `anchor` point sits at `at`.
  Math `glyphs` are the formula's outlines for backends without LaTeX.

## Validation

- `validate` checks in this order: JSON, then the schema, then names
  (ids, references, groups). The first kind that finds a problem stops
  the run there. A malformed `allow` entry is reported, but the IR is
  still handed on: the picture can be drawn, it just cannot be READY.
- Spaces, defs and objects share one set of ids.
- An object belongs to at most one group, a group never ends up inside
  itself, and defs are never group members.
- A header style may only name header colors. A mix in `extra_colors`
  mixes two header colors or literal colors, never `"none"` and never
  another extra color.

## Resolve

- An object inside a group is drawn inside that group, at the group's
  place in the list; members follow the group's `children` order, then
  are sorted by `z`.
- `normalize` runs the cascade before `resolve`: every object leaves it
  with its colors in hex (or `"none"`), its opacity, stroke width, dash
  and, for a text, its size in reference pixels, and with no style
  classes. `resolve` reads paint only from the object itself.
- A mix is the average of its two colors' channels, rounded to the
  nearest integer (halves to even).
- A text is measured by the configured text measurer, and its box is
  placed so that its `anchor` point sits at `at`. Vertically, `center`
  is the middle of the box from descent to ascent.
- An object that paints nothing (no stroke color and no fill) still gets
  its LIR group, with no primitives in it.

## Backends

- A backend lists the LIR features it can draw (`quadratic`, `cubic`,
  `dash`, `evenodd`, `transform`, `text`, `math`, `image`). Straight
  lines, fills and opacity every backend must draw. `math` means
  typesetting TeX itself; a formula that carries glyph outlines needs no
  capability.
- The `render` stage checks the LIR first. A feature the chosen backend
  cannot draw is an `E-CAPABILITY` issue naming the feature and the
  objects that use it, never the backend; nothing is drawn.
- The SVG backend writes `frame.svg` in output pixels (origin top left,
  y down), every IR object as a `<g id>` with its IR path in
  `data-source`, and rasterizes it to `frame.png` at the same size. A
  missing rasterizer is an `E-ENVIRONMENT` issue; `frame.svg` is still
  written.
- SVG text sits at `at` horizontally, aligned by its anchor (start,
  middle, end), and on the measured baseline vertically. Its font is the
  LIR's font, falling back to the system's sans-serif.

## Expressions

- Every number of geometry may be written as text, an expression:
  positions, radii, widths and heights, corner radii, angles, rotations,
  and group transforms. Every other number (the header, opacities,
  stroke widths, dashes, `z`, type sizes) must be a JSON number; text
  there is an `E-SCHEMA` error and is never converted. `true` and `false`
  are the only booleans.
- The language is what sympy prints: numbers (`12`, `0.5`, `1.5e-3`),
  `+ - * / **` and parentheses, `pi` and `E`, and `sqrt`, `sin`, `cos`,
  `tan`, `asin`, `acos`, `atan`, `atan2`, `exp`, `log` (`log(x)` natural,
  `log(x, b)` base b), `Abs`, `Min`, `Max`. `^` is not a power. Trig
  functions use radians, while the IR's angle fields are degrees.
- Arithmetic is exact where it can be: `+ - * /` and whole powers of
  fractions, and the square root of a perfect square, stay fractions;
  anything with `pi`, `E`, another function or another root becomes a
  float from there on. The stored value is the nearest float.
- Names in an expression refer to the body's `values` table. Values may
  use each other, written in any order, but not in a loop (`E-CYCLE`);
  they stay exact between each other, and they cannot be named after a
  constant or a function.
- A result must be a finite real number. Division by zero, the root of a
  negative number, the log of a number that is not positive, `asin` or
  `acos` outside -1…1 are `E-EXPR` errors, with the field's path.

## Header lock

- The header's hash is the SHA-256 of its validated content written as
  compact JSON with sorted keys; spacing, key order and `9` against `9.0`
  do not change it.
- `check_header` compares the IR's header with the one the orchestrator
  locked. A difference is an `E-HEADER` error that lists the changed
  fields (the first five).
