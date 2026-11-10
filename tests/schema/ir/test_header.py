"""The header and the body: the analysis's draft validates, and the two halves stay apart."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from irpipe.canvas import Canvas
from irpipe.schema.ir import (
    BODY_FIELDS,
    HEADER_FIELDS,
    FrameHeader,
    IRBody,
    IRDocument,
    IRHeader,
)
from irpipe.schema.render_profile import RenderProfile

DATA = Path(__file__).parents[2] / "data"

# The header draft of the analysis (§2.1), as it is printed there, without its comments.
ANALYSIS_DRAFT: dict[str, Any] = json.loads(
    (DATA / "analysis_header_draft.json").read_text(encoding="utf-8")
)


def draft(**changes: Any) -> dict[str, Any]:
    """A deep copy of the draft with top-level fields replaced."""
    return {**copy.deepcopy(ANALYSIS_DRAFT), **changes}


def test_the_analysis_header_draft_validates_and_round_trips() -> None:
    document = IRDocument.model_validate(ANALYSIS_DRAFT)
    written = document.model_dump(mode="json", exclude_unset=True)  # what the draft gives
    assert written == ANALYSIS_DRAFT
    assert list(written) == list(ANALYSIS_DRAFT)  # same field order


def test_header_and_body_are_separate_models_that_join_back() -> None:
    document = IRDocument.model_validate(ANALYSIS_DRAFT)
    header, body = document.header, document.body
    assert isinstance(header, IRHeader)
    assert isinstance(body, IRBody)
    assert IRDocument.join(header, body) == document


def test_no_field_belongs_to_both_halves() -> None:
    assert set(HEADER_FIELDS).isdisjoint(BODY_FIELDS)
    assert set(HEADER_FIELDS) | set(BODY_FIELDS) == set(IRDocument.model_fields)


def test_the_header_model_refuses_body_fields() -> None:
    header_only = {name: ANALYSIS_DRAFT[name] for name in HEADER_FIELDS}
    IRHeader.model_validate(header_only)
    with pytest.raises(ValidationError, match="objects"):
        IRHeader.model_validate({**header_only, "objects": []})


def test_the_body_model_refuses_header_fields() -> None:
    with pytest.raises(ValidationError, match="colors"):
        IRBody.model_validate({"objects": [], "colors": {"a": "#FFD43B"}})


def test_another_version_is_refused() -> None:
    with pytest.raises(ValidationError, match=r"frame-ir/1\.0"):
        IRDocument.model_validate(draft(version="frame-ir/0.9"))


@pytest.mark.parametrize(
    "subtitle",
    [
        {"mode": "none", "lines": 2, "band": [-4, -5, 4, -4]},
        {"mode": "reserve", "lines": 2},
    ],
)
def test_a_band_is_given_exactly_when_there_are_subtitles(subtitle: dict[str, Any]) -> None:
    frame = {**ANALYSIS_DRAFT["frame"], "subtitle": subtitle}
    with pytest.raises(ValidationError, match="band is given exactly when"):
        IRDocument.model_validate(draft(frame=frame))


def test_every_text_role_needs_a_size() -> None:
    typography = copy.deepcopy(ANALYSIS_DRAFT["typography"])
    del typography["sizes"]["caption"]
    with pytest.raises(ValidationError, match="caption"):
        IRDocument.model_validate(draft(typography=typography))


def test_none_cannot_name_a_color() -> None:
    with pytest.raises(ValidationError, match="means no paint"):
        IRDocument.model_validate(draft(colors={"none": "#000000"}))


def test_extra_colors_may_mix_two_others() -> None:
    document = IRDocument.model_validate(draft(extra_colors={"AB": {"mix": ["a", "b"]}}))
    assert "AB" in document.extra_colors


def test_the_canvas_numbers_fit_the_frame_header() -> None:
    profile = RenderProfile(aspect="9:16", platform="tiktok", subtitle={"mode": "reserve"})
    canvas = Canvas.from_profile(profile)
    band = canvas.subtitle_band
    assert band is not None
    FrameHeader(
        aspect=profile.aspect,
        pixels=canvas.pixels,
        units=canvas.units,
        platform=profile.platform,
        background=profile.theme.background,
        subtitle={"mode": "reserve", "lines": 2, "band": (band.x0, band.y0, band.x1, band.y1)},
        safe=(canvas.safe.x0, canvas.safe.y0, canvas.safe.x1, canvas.safe.y1),
    )
