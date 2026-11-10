"""The data the picture pipeline's stages hand to each other.

Stages never import each other; they import these keys. A stage's
``requires`` and ``provides`` then read as the data flow:

    ir_source --validate--> ir --resolve--> lir --render--> frame.svg, frame.png
                                               out_dir --^
"""

from pathlib import Path

from irpipe.core import ArtifactKey
from irpipe.schema.ir import IRDocument
from irpipe.schema.lir import LIRDocument

IR_SOURCE = ArtifactKey("ir_source", str, "ir.json as text, exactly as it was written")
IR = ArtifactKey("ir", IRDocument, "the IR, parsed and checked by validate")
LIR = ArtifactKey("lir", LIRDocument, "the resolved draw list that backends draw")
OUT_DIR = ArtifactKey("out_dir", Path, "the run folder the backend writes its files into")
RENDERED = ArtifactKey("rendered", tuple, "the files the backend wrote, as Paths")
