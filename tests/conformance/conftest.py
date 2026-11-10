"""The bench the conformance tests stand on: one LIR, drawn by both backends, compared.

The SVG backend is the reference (analysis §3): Manim's frame.png must
match its frame.png pixel for pixel, within what antialiasing leaves.

    drawn = bench.lir([group("a", path)])        # a LIR drawn by both backends
    drawn = bench.ir(ir_text([...]))             # an IR through the whole front-end
    drawn.assert_alike()                         # outside texts: the same picture
    drawn.assert_texts_alike()                   # texts: in the same place

Texts are compared apart: the SVG backend lets cairosvg set them, Manim
lets Pango (which measured them), so the glyphs differ slightly in width
and weight. A text's box is masked out of the pixel comparison, and its
ink must sit in the same place instead, within ``TEXT_EDGE_PX`` px plus
``TEXT_EDGE_SHARE`` of its size.

When a comparison fails, the two pictures and their difference are kept
in the test's tmp folder and named in the message.
"""

import importlib.util
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from irpipe.artifacts import IR, IR_SOURCE, LIR, OUT_DIR
from irpipe.backends.render import Render
from irpipe.core import Pipeline, Report, load_config
from irpipe.core.plugins import load_plugins
from irpipe.frontend.geometry import affine
from irpipe.schema.lir import Box as UnitBox
from irpipe.schema.lir import Group, LIRDocument, TextItem

ROOT = Path(__file__).parent.parent.parent
CANVAS: dict[str, Any] = {"units": [16, 9], "pixels": [1920, 1080], "background": "#0E1117"}

INK = 32
"""A pixel is ink when one of its channels is this far from the background."""
STRONG = 128
"""Two pixels disagree when one of their channels differs by more than this."""
MAX_STRONG_SHARE = 0.001
"""At most this share of the ink pixels may disagree (antialiasing on curves)."""
MAX_MEAN = 0.1
"""The mean difference over the whole frame, on 0-255, outside texts."""
TEXT_MARGIN_PX = 4
"""How far around a text's box the pixel comparison looks away."""
TEXT_EDGE_PX = 1.5
TEXT_EDGE_SHARE = 0.03
"""A text's ink edges may differ by 1.5 px plus 3% of its extent along that axis."""

type Pixels = Any  # numpy array, height x width x 3, int
type Box = tuple[int, int, int, int]  # left, top, right, bottom, in pixels


@dataclass
class Drawn:
    """One LIR as both backends drew it."""

    lir: LIRDocument
    svg: Pixels
    manim: Pixels
    folder: Path

    def ink(self) -> Pixels:
        background = np.array([int(self.lir.canvas.background[k : k + 2], 16) for k in (1, 3, 5)])
        apart = [np.abs(image - background).max(axis=2) > INK for image in (self.svg, self.manim)]
        return apart[0] | apart[1]

    def text_boxes(self) -> list[tuple[str, Box]]:
        """Every text's box in output pixels, with its group's id."""
        (width, height), (units_w, units_h) = self.lir.canvas.pixels, self.lir.canvas.units
        kx, ky = width / units_w, height / units_h
        boxes = []
        for gid, (x0, y0, x1, y1) in _texts(self.lir):
            left, right = width / 2 + x0 * kx, width / 2 + x1 * kx
            top, bottom = height / 2 - y1 * ky, height / 2 - y0 * ky
            boxes.append((gid, (int(left), int(top), int(np.ceil(right)), int(np.ceil(bottom)))))
        return boxes

    def text_mask(self) -> Pixels:
        mask = np.zeros(self.svg.shape[:2], dtype=bool)
        for _, (left, top, right, bottom) in self.text_boxes():
            m = TEXT_MARGIN_PX
            mask[max(top - m, 0) : bottom + m, max(left - m, 0) : right + m] = True
        return mask

    def assert_alike(self) -> None:
        """Outside texts, the two pictures are the same up to antialiasing."""
        difference = np.abs(self.svg - self.manim).max(axis=2)
        outside = ~self.text_mask()
        ink = int((self.ink() & outside).sum())
        strong = int(((difference > STRONG) & outside).sum())
        mean = float(difference[outside].mean())
        if strong > MAX_STRONG_SHARE * max(ink, 1) or mean > MAX_MEAN:
            path = self._keep(difference)
            pytest.fail(
                f"the backends disagree: {strong} of {ink} ink pixels differ by more than "
                f"{STRONG} (at most {MAX_STRONG_SHARE:.1%} may), mean difference {mean:.3f} "
                f"(at most {MAX_MEAN}); pictures in {path}"
            )

    def assert_texts_alike(self) -> None:
        """Every text's ink sits in the same place in both pictures."""
        problems = []
        for gid, box in self.text_boxes():
            svg, manim = _ink_box(self.svg, box, self.lir), _ink_box(self.manim, box, self.lir)
            if svg is None or manim is None:
                problems.append(f"'{gid}' draws nothing in {'svg' if svg is None else 'manim'}")
                continue
            extents = (svg[2] - svg[0], svg[3] - svg[1]) * 2  # width, height, width, height
            for edge, (a, b, extent) in enumerate(zip(svg, manim, extents, strict=True)):
                allowed = TEXT_EDGE_PX + TEXT_EDGE_SHARE * extent
                if abs(a - b) > allowed:
                    side = ("left", "top", "right", "bottom")[edge]
                    problems.append(f"'{gid}' {side}: svg {a}, manim {b} (allowed {allowed:.1f})")
        if problems:
            path = self._keep(np.abs(self.svg - self.manim).max(axis=2))
            pytest.fail("texts are not in the same place: " + "; ".join(problems) + f" ({path})")

    def _keep(self, difference: Pixels) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        image = Image.fromarray(np.clip(difference * 3, 0, 255).astype(np.uint8))
        image.save(self.folder / "difference.png")
        return self.folder


class Bench:
    """Draws a LIR, or an IR through the front-end, with both backends."""

    def __init__(self, folder: Path, cache: Path) -> None:
        self.folder = folder
        self.cache = cache
        load_plugins(["irpipe.backends"])  # a bare LIR is drawn without the rest of the pipeline

    def lir(self, items: list[dict[str, Any]], canvas: dict[str, Any] | None = None) -> Drawn:
        drawing = LIRDocument.model_validate({"canvas": canvas or CANVAS, "items": items})
        return self.lir_document(drawing)

    def ir(self, text: str) -> Drawn:
        config = load_config(ROOT / "pipeline.toml")
        load_plugins(config.pipeline.plugins)
        stages = [s for s in config.pipeline.stages if s != "render"]
        result = Pipeline.build(stages, inputs=[IR_SOURCE, OUT_DIR], options=config.options).run(
            {IR_SOURCE: text, OUT_DIR: self.folder}
        )
        allows = result.get(IR).allow if IR.name in result.artifacts else ()
        report = Report.build(result.issues, allows=allows, stopped_at=result.stopped_at)
        assert report.ready, report.issues
        return self.lir_document(result.get(LIR))

    def lir_document(self, drawing: LIRDocument) -> Drawn:
        svg, manim = self._render(drawing, "svg"), self._render(drawing, "manim")
        return Drawn(drawing, svg, manim, self.folder)

    def _render(self, drawing: LIRDocument, backend: str) -> Pixels:
        out = self.folder / backend
        settings = {"cache_dir": str(self.cache)} if backend == "manim" else {}
        options = {"render": {"backend": backend, backend: settings}}
        result = Pipeline([Render()], inputs=[LIR, OUT_DIR], options=options).run(
            {LIR: drawing, OUT_DIR: out}
        )
        assert result.issues == (), result.issues
        return np.asarray(Image.open(out / "frame.png").convert("RGB")).astype(int)


@pytest.fixture(scope="session")
def manim_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One cache for the session, so each formula is typeset once."""
    return tmp_path_factory.mktemp("manim-cache")


@pytest.fixture
def bench(tmp_path: Path, manim_cache: Path) -> Iterator[Bench]:
    for package in ("manim", "cairosvg"):
        if importlib.util.find_spec(package) is None:
            pytest.skip(f"the conformance tests need {package}")
    yield Bench(tmp_path, manim_cache)


@pytest.fixture
def group() -> Callable[..., dict[str, Any]]:
    """``group(id, *children, **fields)``: one LIR group as a dict."""
    return lambda gid, *children, **fields: {
        "type": "group",
        "id": gid,
        "children": list(children),
        **fields,
    }


def _texts(drawing: LIRDocument) -> list[tuple[str, UnitBox]]:
    """Every text item's box in the frame (group transforms applied), with its group's id."""
    found: list[tuple[str, UnitBox]] = []

    def visit(group: Group, matrix: affine.Matrix) -> None:
        matrix = affine.compose(matrix, group.transform)
        for node in group.children:
            if isinstance(node, Group):
                visit(node, matrix)
            elif isinstance(node, TextItem):
                found.append((group.id, affine.transform_box(matrix, node.box)))

    for item in drawing.items:
        visit(item, affine.IDENTITY)
    return found


def _ink_box(image: Pixels, box: Box, drawing: LIRDocument) -> Box | None:
    """The box of the ink inside ``box`` (with the margin), in pixels; None when blank."""
    background = np.array([int(drawing.canvas.background[k : k + 2], 16) for k in (1, 3, 5)])
    left, top, right, bottom = box
    m = TEXT_MARGIN_PX
    region = image[max(top - m, 0) : bottom + m, max(left - m, 0) : right + m]
    rows, cols = np.nonzero(np.abs(region - background).max(axis=2) > STRONG)
    if len(rows) == 0:
        return None
    x0, y0 = max(left - m, 0), max(top - m, 0)
    return (
        x0 + int(cols.min()),
        y0 + int(rows.min()),
        x0 + int(cols.max()) + 1,
        y0 + int(rows.max()) + 1,
    )
