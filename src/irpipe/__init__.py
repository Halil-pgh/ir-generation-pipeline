"""irpipe: turns a frame brief into a picture through a library-independent IR.

The pipeline is a chain of pluggable stages (``irpipe.core``, added in step 1)
whose order and contents come from ``pipeline.toml``. This module only holds
the package version, which ``pyproject.toml`` reads as its single source.
"""

__version__ = "0.1.0"
