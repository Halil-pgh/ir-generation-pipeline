"""Backends: the library-specific half, which only draws a LIR (analysis §3).

A backend is a plugin. It says which LIR features it can draw (its
capabilities) and turns a LIR into files. The ``render`` stage picks one
by name from ``pipeline.toml``; listing ``irpipe.backends`` under
``plugins`` loads them all.

Module map:
    base.py    Backend, Capability, BACKENDS; E-CAPABILITY and E-ENVIRONMENT
    render.py  stage "render": LIR -> the chosen backend's files
    svg/       the SVG reference backend: frame.svg, and frame.png through cairosvg
"""
