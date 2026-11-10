"""Geometry the front-end computes so that backends never have to.

Module map:
    affine.py   2D affine matrices: compose, invert, apply, boxes through a matrix
    curves.py   lengths, points, directions, bounds, trimming and flattening of LIR subpaths
    areas.py    subpaths <-> shapely areas and lines; fill rules; half planes, graph areas
    flood.py    flood fill: the face of the plane the boundary lines close around a seed
    clip.py     a shape's fill and stroke cut by a mask
"""
