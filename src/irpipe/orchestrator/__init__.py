"""The orchestrator: deterministic code that runs one frame from brief to run folder (analysis §1).

It is not an LLM. It reads the planner's brief, locks the IR's header,
checks the tools, runs the agent's build_ir.py, compiles and draws the IR
it wrote, and sends what went wrong where it belongs: the agent, the
planner or a person. ``irpipe run brief.json build_ir.py`` is its command.

Module map:
    run.py          orchestrate(): the whole run, step by step; E-INTERNAL
    inputs.py       the brief and its lesson plan, read; the frame's style and header; E-BRIEF
    header.py       header_for(): the locked header from a brief and its style
    environment.py  fonts, LaTeX and packages this picture needs; E-ENVIRONMENT
    script.py       run_script(): build_ir.py writes ir.json; E-SCRIPT
    coverage.py     coverage_issues(): every must_show item covered; W-UNCOVERED
    routing.py      route(): who acts next (done, agent, planner, human)
    records.py      meta.json and alt.txt
"""
