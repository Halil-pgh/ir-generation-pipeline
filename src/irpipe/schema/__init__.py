"""The data contracts of the pipeline, as pydantic models.

Every document that crosses a boundary (the render profile, the brief, the
IR, the LIR) is a model here. JSON Schema and the spec are generated from
these models (step 5), so the models are the single source of truth.

Module map:
    render_profile.py  RenderProfile: aspect, resolution, platform, margins,
                       subtitle, typography and theme of one picture
    brief.py           LessonPlan and FrameBrief: what the planner hands on;
                       frame_style(): the lesson's style with a frame's changes
    ir/                IR 1.0: header, body and the core objects
    lir.py             LIR 1.0: the resolved draw list backends draw
    spec.py            writes the JSON Schema of every contract to docs/spec/
    color.py           Color, ColorRef: how contracts write colors
    base.py            StrictModel: immutable, refuses unknown fields
"""
