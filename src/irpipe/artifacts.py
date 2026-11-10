"""The data the picture pipeline's stages hand to each other.

Stages never import each other; they import these keys. A stage's
``requires`` and ``provides`` then read as the data flow:

    ir_source --validate--> ir --resolve--> lir --backend--> frame.png
"""

from irpipe.core import ArtifactKey
from irpipe.schema.ir import IRDocument
from irpipe.schema.lir import LIRDocument

IR_SOURCE = ArtifactKey("ir_source", str, "ir.json as text, exactly as it was written")
IR = ArtifactKey("ir", IRDocument, "the IR, parsed and checked by validate")
LIR = ArtifactKey("lir", LIRDocument, "the resolved draw list that backends draw")
