"""The data contracts of the pipeline, as pydantic models.

Every document that crosses a boundary (the render profile, the brief, the
IR, the LIR) is a model here. JSON Schema and the spec are generated from
these models (step 5), so the models are the single source of truth.

Module map:
    render_profile.py  RenderProfile: aspect, resolution, platform, margins,
                       subtitle, typography and theme of one picture
"""
