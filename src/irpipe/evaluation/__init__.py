"""Measuring the pipeline (analysis §8): regression over our examples, and the eval matrix.

    result = regress(Path("examples"), Path("runs/regression"))      # irpipe regress
    result = evaluate(Path("eval/lessons.toml"), Path("evals/lessons"))   # irpipe eval

**Regression** has no model in it: every example of examples/ is drawn
again and compared, pixel by pixel, with the picture it had when it was
last accepted (decision K27: our own examples, not an earlier project's).
**The eval** runs the language models: topics x aspects x model pairs x
repeats, each cell a lesson planned and drawn; it counts the frames that
come out READY, the turns, the returns to the planner, the cost and the
time, and shows every frame in a gallery. Both run many at once, each run
in a process of its own.

Module map:
    images.py      two pictures compared (Pillow and numpy, from the manim extra)
    configs.py     a pipeline.toml for one worker: changes, its own Manim cache
    regression.py  cases_in(), regress(): examples drawn and compared
    matrix.py      EvalMatrix, read_matrix(): the eval file, its cells
    cells.py       run_cell(): one lesson as a cell says, and its numbers
    run.py         evaluate(): every cell at once, results.json
    summary.py     summary.md and gallery.html
"""

from irpipe.evaluation.cells import CellResult, FrameResult, run_cell
from irpipe.evaluation.matrix import Cell, EvalMatrix, ModelPair, read_matrix
from irpipe.evaluation.regression import CaseResult, RegressionResult, cases_in, regress
from irpipe.evaluation.run import EvalResult, evaluate

__all__ = [
    "CaseResult",
    "Cell",
    "CellResult",
    "EvalMatrix",
    "EvalResult",
    "FrameResult",
    "ModelPair",
    "RegressionResult",
    "cases_in",
    "evaluate",
    "read_matrix",
    "regress",
    "run_cell",
]
