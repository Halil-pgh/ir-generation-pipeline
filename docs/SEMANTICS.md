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
  part of an object (`v.label`) or one of its points (`v.tip`), so ids
  never contain one.
- `zones` are named boxes `[left, bottom, right, top]` other objects may
  refer to (`"plot.left_top"`); they are not drawn.

## Paint

- Paint fields left out are inherited, in this order: theme defaults,
  then the object's style classes in the order listed (a later class
  wins), then the object's own fields.
- The theme defaults are the header's `theme`: texts take its `text`
  color, regions and flood fills no color (they are not outlined unless
  they give one), every other object its `line` color, every stroke its
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
- A group's children are ids of other objects. Its transform is applied
  as: scale, then rotate (degrees, counterclockwise), both about `pivot`;
  then translate. It turns and scales the children's drawings, strokes
  and texts included. `pivot` is in the group's own coordinates.
- A stack's children are ids of other objects, laid out as a `column`
  (the default), a `row` or a `grid` of `columns`; see Placement.
- `line`, `polyline`, `arc` and `path` may carry `arrows` at their
  `start`, their `end` and `mid`way along. A head is a filled triangle in
  the line's color, pointing the way the line runs (at the start,
  backwards), `arrow_size` reference px long (4 x the stroke width + 10
  when left out) and 0.8 of that wide; the line stops 0.6 of a head's
  length short of the tip. A line that paints nothing has no heads.
- Every shape may carry a `label` (see Placement).
- A `region` is an area built from other objects, and a `flood_fill` the
  part of the plane lines enclose around a seed; any object may be drawn
  only inside an area (`clip`) or only outside one (`clip_out`). See
  Regions.

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
- Spaces, zones, defs and objects share one set of ids; `frame` and
  `safe` are taken by the picture's own boxes.
- An object belongs to at most one group or stack, neither ever ends up
  inside itself, and defs are never members.
- Every reference names something that has that point: an object, a
  label (`v.label`), a zone, `frame` or `safe` for `"id.anchor"`, a shape
  for `{"on": ...}`. `in` names a space, `next_to` another object or a
  zone, and a label's `at` a point its owner has.
- A region's operands (and a clip's) are objects or defs with an inside:
  closed shapes, regions and flood fills. A graph (`under`, `between`) and
  a flood fill's boundary may be any shape, open or closed. Anything else
  is `E-REGION`; a name that points at nothing is `E-REF`.
- A header style may only name header colors. A mix in `extra_colors`
  mixes two header colors or literal colors, never `"none"` and never
  another extra color.

## Placement

- Positions and lengths are in frame units, or in the units of the space
  an object names with `in`. Type sizes, stroke widths, dashes and arrow
  sizes are always reference px.
- A space maps its point (x, y) to `origin + (x * ux, y * uy)`, where
  `unit` is `ux` (and `uy`); lengths scale the same way, so a circle in a
  space with two different scales is drawn as an ellipse. The map takes
  the object into the coordinates it is drawn in: the frame, or its
  group's content. A space's `origin` may be a reference (a point of the
  frame).
- A point is `[x, y]` or a reference. `"id.anchor"` names a point of an
  object, a label, a zone, `frame` (the whole picture) or `safe` (the
  header's safe area). `{"on": id, "t": t}` is the point `t` of the way
  along a shape's outline by length (0 its start, 1 its end; moving from
  one subpath to the next adds nothing); `{"on": id, "x": x}` the first
  point, in drawing order, where the outline reaches `x` in the shape's
  own coordinates. An `x` it never reaches is `E-PLACE`.
- Anchors: every object, zone, `frame` and `safe` has the nine points of
  its box: `left_top`, `center_top`, `right_top`, `left_center`,
  `center`, `right_center`, `left_bottom`, `center_bottom`,
  `right_bottom`. Texts, formulas and stacks also have `left_baseline`,
  `center_baseline` and `right_baseline`. For a circle, ellipse,
  rectangle, regular polygon, arc or sector, `center` is its `center`
  field. A line, polyline, arc or path has `start`, `end` and `mid`
  (halfway along by length); `tail` and `tip` are `start` and `end`.
- A shape's box is its geometry's, without the stroke; its baseline is
  its bottom. A group's box surrounds its children's boxes after the
  group's transform. Box points of a turned object are its own box's
  points, turned with it.
- A reference is read in the picture: whatever spaces, groups and stacks
  the two objects are in, the point lands exactly on the anchor. The one
  exception is a group's `pivot` naming something inside that group: it
  is read in the group's content, before the group turns it. Positions
  may name objects written later; positions that depend on each other in
  a loop are `E-CYCLE`.
- A text, formula or stack is a box placed one of three ways: `at` with
  `anchor` (the `anchor` point of the box sits at `at`; `center` when left
  out); `at` with `dir` (the box sits beside the point); `next_to` with
  `dir` (the box sits beside another object's box or a zone; `dir` is
  `right` when left out). Beside means: on the ray from the point (or the
  other box's center) in direction `dir`, with `gap` (0.2 units when left
  out) between the two along that ray. `dir` is `up`, `down`, `left`,
  `right`, `up_left`, `up_right`, `down_left`, `down_right`, an angle in
  degrees, or `[dx, dy]`. Inside a turned group, directions turn with it.
- A box with no place that is not in a stack is `E-PLACE`, and so is a
  stack child that gives `at` or `next_to`: the stack places it.
- A stack lays out its children in reading order. A column is as wide as
  its widest child and a row as tall as its tallest; `spacing` (0.25
  units, or `[between columns, between rows]`) separates cells. Each
  child sits in its cell so that its `align` point meets the cell's
  (`center` when left out); a vertical part `baseline` lines a row up on
  one baseline, and the row is then tall enough for its highest ascent
  and deepest descent together. The stack's box surrounds the cells, and
  its baseline is its first child's. After placing, a stack is a group of
  its children.
- A shape's `label` is drawn as the text or formula `<id>.label`, at the
  owner's point `at` (`center` when left out): beside it with `dir` and
  `gap`, centered on it without. It takes the owner's color (its stroke,
  else its fill) and opacity, the `label` size and the owner's `z`,
  unless it says otherwise. It is drawn in the owner's group right after
  the owner, or, outside groups, after every other object.

## Regions

- A region's `shape` is an area: an object's id (its inside), or
  `{"union": [...]}`, `{"intersection": [...]}`, `{"difference": [first,
  ...]}` (the first without the others), `{"xor": [a, b]}` (in exactly
  one), `{"half_plane": [p, q]}` (left of the line from p to q),
  `{"under": f, "x": [x0, x1]}` (between graph f and its y = 0) or
  `{"between": [f, g], "x": [x0, x1]}`. Expressions nest. A graph's x and
  y = 0 are in its own coordinates; it is read from the first point that
  reaches x0 to the first that reaches x1 (a graph meets each x once). A
  graph that does not reach an x is `E-REGION`.
- A flood fill's `bounded_by` lines cut the plane where they cross; the
  face that holds `seed` is painted. Lines may be open and may run on past
  a crossing. A seed on a line, or in a part the lines leave open, is
  `E-REGION`. A closed line inside the face leaves a hole.
- The place stage computes every area in the frame and writes it as a
  path in the object's own coordinates, holes and all, drawn even-odd. So
  a region has anchors, a label and a place in groups like any shape, and
  may be another region's operand. A region or flood fill that comes out
  empty is `W-EMPTY-REGION` and draws nothing.
- Areas are computed on straight pieces: curves are cut into 64 per
  quarter circle, closer than a hundredth of a pixel at the usual sizes,
  and a computed area's outline is straight pieces. A shape's inside
  follows its fill rule as SVG does: of the faces its subpaths cut the
  plane into, even-odd keeps those an odd number of subpaths go round,
  nonzero those the subpaths' turns do not cancel out on.
- `clip` (or `clip_out`) on an object or a group draws it only inside
  (only outside) the area. Place writes each clip as a def
  `<id>.clip` (`<id>.clip_out`), a path in the frame, and the field names
  it. A group's clip reaches everything inside it, and clips inside clips
  meet. Fills and strokes are cut geometrically, each on its own; a cut
  line ends flat at the area's edge. A shape wholly inside keeps its
  curves and hint; one wholly outside draws nothing. Texts and formulas
  are drawn whole, with `W-CLIP-TEXT`.

## Resolve

- `resolve` draws the placed IR: every position is already a number.
- An object inside a group is drawn inside that group, at the group's
  place in the list; members follow the group's `children` order, then
  are sorted by `z`.
- `normalize` runs the cascade before `resolve`: every object leaves it
  with its colors in hex (or `"none"`), its opacity, stroke width, dash
  and, for a text, its size in reference pixels, and with no style
  classes. `resolve` reads paint only from the object itself.
- A mix is the average of its two colors' channels, rounded to the
  nearest integer (halves to even).
- A text or formula is placed by the box `measure` gave it, so that its
  `anchor` point sits at `at`. Vertically, `center` is the middle of the
  box from descent to ascent.
- An object in a space has its points mapped here, so its stroke width is
  untouched. Its hint follows: under two different scales a circle's
  becomes an ellipse's, and a regular polygon, arc or sector goes without
  one. A line or polyline with arrows keeps a hint with its cut ends;
  other shapes with arrows go without one.
- An object that paints nothing (no stroke color and no fill) still gets
  its LIR group, with no primitives in it.

## Checks

- The `check` stage runs after `resolve`, on what was drawn (the LIR),
  with the IR at hand for what was meant (references, groups, the frame,
  the safe area, the subtitle band). `pipeline.toml` lists the checks
  that run (`[options.check] checks`; every registered check when the
  list is left out) and gives each its settings
  (`[options.check.<name>]`); a misspelled name or setting is refused.
- A check's findings never stop the run: the picture is still drawn, and
  the report says whether it is READY. Every finding names the object in
  IR terms, its id and its JSON path.
- What an object covers: a path's geometry, its strokes at their width;
  a text's measured box; a formula's ink box. Group transforms are
  applied. Lengths are in units, sizes in reference px.
- Two objects are related on purpose when one is placed by a reference
  to the other (`"v.tip"`, `{"on": ...}`, `next_to`), one is built from
  the other (a region's operands, a flood fill's lines, a clip), or both
  are in the same group or stack. Related objects may overlap; checks of
  readability ignore relations.
- `offscreen` (`W-OFFSCREEN`) and `safe_area` (`W-UNSAFE`): an object
  reaches past the frame or the safe area by more than 0.001 units; each
  edge is named with how far.
- `subtitle` (`E-SUBTITLE`): an object covers part of the subtitle band
  (more than touching its edge).
- `text_overlap` (`W-TEXT-OVERLAP`): the boxes of two texts or formulas
  overlap.
- `text_crossed` (`W-TEXT-CROSSED`): a stroked line of another object runs
  more than 0.02 units inside a text's or formula's box, taken a tenth of
  its height smaller all round; whether drawn over the text or under it.
- `contrast` (`W-LOW-CONTRAST`): the WCAG contrast between a text and the
  color behind it falls below 4.5:1 (3:1 from 48 px). The color behind is
  the background with every fill drawn earlier laid over it at its
  opacity; the text is mixed with it at its own opacity; the worst of a
  3 x 3 grid of points in the box counts.
- `text_size` (`W-SMALL-TEXT`): a text or formula is set below 28 px.
- `similar_colors` (`W-SIMILAR-COLORS`): two different colors something is
  painted with (fill, stroke, text) differ by less than 10 in CIEDE2000.
- `fill_overlap` (`W-FILL-OVERLAP`): the fills of two unrelated objects
  overlap over more than 2% and less than 98% of the smaller one (less is
  touching; more is one lying inside the other, which is layering).
- `group_opacity` (`W-GROUP-OPACITY`): a group or stack with opacity below
  1 has children that overlap, so they show through each other.
- `glyphs` (`W-MISSING-GLYPH`): a text uses a character the font fontconfig
  picks for it has no glyph for. Without fontconfig nothing is reported.
- Every warning above may be accepted with `allow`, except
  `W-MISSING-GLYPH`: an empty box is never what was meant.

## Backends

- A backend lists the LIR features it can draw (`quadratic`, `cubic`,
  `dash`, `evenodd`, `transform`, `text`, `math`, `image`). Straight
  lines, fills and opacity every backend must draw. `math` means drawing
  formula items, setting the TeX itself.
- The `render` stage lowers the LIR for the chosen backend before it
  draws: every feature the backend does not list is rewritten with
  simpler ones. `lir.json` stays the LIR before lowering, the same for
  every backend.
  - Cubic curves become quadratic curves, else straight segments, and
    quadratic curves become cubic curves (exactly), else straight
    segments; nothing strays more than 0.001 units from the curve. A
    shape's hint is kept.
  - A dashed stroke becomes one plain path per dash, laid out as SVG
    lays them: the pattern (repeated once more when its count is odd)
    starts afresh on each subpath and runs on across its segments,
    closing edge included. A filled shape becomes its fill (hint kept)
    and its dashes, drawn after it.
  - An even-odd fill becomes a nonzero fill of the same area: subpaths
    that do not cross are turned (counterclockwise inside an even number
    of others, clockwise inside an odd number) and keep their curves;
    crossing ones are recomputed as polygons with their holes.
  - Group transforms are applied to the children's numbers and every
    group's transform becomes the identity. Stroke widths and dashes
    scale by the square root of the transform's area factor. Hints stay
    under a shift and per-axis scale, and are dropped otherwise. A text
    or formula follows a shift and an even scale (its size scales).
  - Formulas become their glyph outlines, filled in the formula's color
    and opacity, where TeX cannot be set, and wherever a group turns or
    stretches them and transforms cannot be drawn.
- What cannot be lowered is reported in IR terms, naming the object and
  its JSON path, never the backend, and nothing is drawn: a text where
  texts cannot be drawn, a text (or a formula without outlines, or an
  image) that a group turns or stretches where transforms cannot be
  drawn, and an image where images cannot be drawn are `E-CAPABILITY`; a
  formula without glyph outlines where TeX cannot be set is
  `E-ENVIRONMENT` (it was measured without typesetting).
- The SVG backend draws every feature but `math`: formulas reach it as
  their outlines.
- The SVG backend writes `frame.svg` in output pixels (origin top left,
  y down), every IR object as a `<g id>` with its IR path in
  `data-source`, and rasterizes it to `frame.png` at the same size. A
  missing rasterizer is an `E-ENVIRONMENT` issue; `frame.svg` is still
  written.
- SVG text sits at `at` horizontally, aligned by its anchor (start,
  middle, end), and on the measured baseline vertically. Its font is the
  LIR's font, falling back to the system's sans-serif.
- The Manim backend draws `cubic`, `transform`, `text` and `math`.
  Quadratic curves, dashes and even-odd fills reach it lowered (Manim fills
  nonzero); images are not drawn yet.
- It writes `scene.py`, code for Manim Community 0.22.1 that stands on its
  own: `manim -s scene.py Frame` draws the picture. Its frame is the LIR's
  canvas: the units, the output pixels and the background. Every LIR group
  is built by a function `make_<id>()`, with a `# ir: <path> id=<id>`
  comment above it; `construct` keeps what it returns in a variable named
  after the id, and an object holding others receives them as arguments.
  An id that cannot be a Python name, or is one scene.py uses itself,
  changes as little as it can: `a.label` becomes `a_label`, `class`
  becomes `class_`, a clash takes `_2`.
- A path is drawn with the Manim class of its hint (`Circle`, `Line`,
  `Arc`...) with the hint's numbers, but only while the hint describes the
  whole path: one closed subpath for a closed shape, one open subpath with
  the shape's own ends for a line, polyline or arc. Otherwise it is built
  from its subpaths, point by point.
- A stroke width of 1 in Manim is 0.01 units, so a width of `w` reference
  px is written as `w / 1.2`. A group's transform is applied to its
  children, and stroke widths scale by the square root of its area factor,
  as lowering does.
- A text is Manim's `Text` at `font_size` = 0.6 x its size in reference px
  (an em of `font_size / 72` units). Manim keeps no baseline, so the text is
  moved onto its ink box: where Pango, with the front-end's settings, puts
  its glyphs inside the measured box. A text of spaces only draws nothing.
- A formula is `MathTex` set with the front-end's own template, at
  `font_size` = 0.803 x its size (one TeX big point is `font_size / 960`
  units), and moved onto its box, which is already the ink box.
- `frame.png` is drawn by a harness in a process of its own. It builds
  every object on its own first, so a failure names the object: `E-DRAW`
  (origin `internal`, a fault in the compiler) or `E-ENVIRONMENT` (Manim or
  a tool is missing). Then nothing is drawn, but `scene.py` is still
  written. The run folder gets nothing else.

## Expressions

- Every number of geometry may be written as text, an expression:
  positions, radii, widths and heights, corner radii, angles, rotations,
  group transforms, a space's origin and unit, gaps and spacings, and the
  `x` of a point on an outline. Every other number (the header,
  opacities, stroke widths, dashes, `z`, type sizes, arrow sizes, a
  direction's angle or vector, the `t` of a point on an outline) must be
  a JSON number; text there is an `E-SCHEMA` error and is never
  converted. `true` and `false` are the only booleans.
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

## Measurement

- `measure` sizes every text and formula before `resolve`, with the
  measurer `pipeline.toml` names. `pango` measures text with Pango, as
  Manim draws it, and formulas with LaTeX; `fixed` needs neither and
  gives every glyph the same width.
- A text's box is the font's: its advance width, and the font's ascent
  and descent, which are the same for every string in that font and
  size. Metrics are not hinted and glyph positions are not rounded, so a
  text twice the size is exactly twice as large.
- A formula is set as `$\displaystyle …$` with the header's math font
  at 10 pt, and its 10 pt em becomes `size` reference pixels. Its box is
  the ink box of its glyphs, on TeX's baseline. Its glyph outlines go
  into the LIR, so a backend without LaTeX can draw it.
- A TeX mistake is `E-TEX`, with LaTeX's own message and the part of the
  formula where it stopped; the run stops at `measure`. A missing
  measurer, LaTeX or dvisvgm is `E-ENVIRONMENT` and also stops it. A
  missing text font is `E-ENVIRONMENT` too, but texts are measured in the
  substitute font and the run goes on.
- Measurements are kept in memory; formulas also in a folder
  (`cache_dir`), written atomically, so it can be shared between runs.
