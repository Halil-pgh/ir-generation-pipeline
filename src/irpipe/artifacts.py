"""The data the picture pipeline's stages hand to each other.

Stages never import each other; they import these keys. A stage's
``requires`` and ``provides`` then read as the data flow:

    ir_source --validate--> ir --normalize--> ir_normal --measure--> measured
    ir_normal, measured --resolve--> lir
    lir, out_dir --render--> frame.svg, frame.png
"""

from pathlib import Path

from irpipe.core import ArtifactKey
from irpipe.schema.ir import IRDocument, IRHeader
from irpipe.schema.lir import LIRDocument

IR_SOURCE = ArtifactKey("ir_source", str, "ir.json as text, exactly as it was written")
IR = ArtifactKey("ir", IRDocument, "the IR, parsed and checked by validate")
IR_NORMAL = ArtifactKey(
    "ir_normal", IRDocument, "the IR with each object's paint written out in full by normalize"
)
MEASURED = ArtifactKey(
    "measured", dict, "id -> TextBox or MathBox of every text and formula, from measure"
)
LIR = ArtifactKey("lir", LIRDocument, "the resolved draw list that backends draw")
OUT_DIR = ArtifactKey("out_dir", Path, "the run folder the backend writes its files into")
RENDERED = ArtifactKey("rendered", tuple, "the files the backend wrote, as Paths")
LOCKED_HEADER = ArtifactKey(
    "locked_header", IRHeader, "the header the orchestrator wrote; the IR must carry it unchanged"
)
