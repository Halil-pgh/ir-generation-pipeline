"""The eval's numbers put together: summary.md for people, gallery.html to look at the frames.

    text = summary(results, title="lessons", wall_seconds=1380)
    page = gallery(results)

The summary gives the whole run (frames READY, the planner's first answers,
returns, cost, time), then the same by aspect, by model pair and by topic,
the issue codes left open in frames that are not READY, and the cells that
failed. READY says the checks found nothing; whether a picture teaches
well is for a person to see, so the gallery shows every frame drawn.
"""

import html
from collections import Counter
from collections.abc import Callable, Iterable
from statistics import mean

from irpipe.evaluation.cells import CellResult


def summary(results: list[CellResult], *, title: str, wall_seconds: float) -> str:
    frames = [f for r in results for f in r.frames]
    drew = any(r.cell.draw for r in results)
    planned = [r for r in results if r.planned]
    first = sum(r.planned and r.answers == 1 for r in results)
    lines = [
        f"# Eval: {title}",
        "",
        f"- Cells: {len(results)}; lessons planned: {len(planned)} of {len(results)}; "
        f"usable at the planner's first answer: {first} of {len(results)}",
    ]
    if drew:
        ready = sum(f.status == "READY" for f in frames)
        lines.append(f"- Frames READY: {ready} of {len(frames)} ({_share(ready, len(frames))})")
        lines.append(f"- Returns to the planner: {sum(r.returns for r in results)}")
    cost = sum(r.cost_usd for r in results)
    planner = sum(r.planner_cost_usd for r in results)
    agent = max(cost - planner, 0.0)
    lines.append(f"- Cost: ${cost:.2f} (planner ${planner:.2f}, agent ${agent:.2f})")
    seconds = [r.seconds for r in results]
    lines.append(
        f"- Time: {wall_seconds / 60:.1f} min in all; a cell {_mean(seconds) / 60:.1f} min on "
        f"average, the longest {max(seconds, default=0) / 60:.1f} min"
    )
    for name, key in (
        ("aspect", lambda r: r.cell.aspect),
        ("models (planner / agent)", lambda r: f"{r.cell.planner} / {r.cell.agent}"),
        ("topic", lambda r: r.cell.topic),
    ):
        lines += ["", f"## By {name}", "", *_table(results, key, drew)]
    if drew:
        left = Counter(code for f in frames if f.status != "READY" for code in f.codes)
        lines += ["", "## Open issues in frames that are not READY", ""]
        lines += [f"- {code}: {count}" for code, count in left.most_common()] or ["- none"]
    failed = [r for r in results if r.error]
    if failed:
        lines += ["", "## Cells that failed", ""]
        lines += [f"- {r.cell.id} ({r.cell.topic}): {r.error}" for r in failed]
    return "\n".join(lines) + "\n"


def _table(results: list[CellResult], key: Callable[[CellResult], str], drew: bool) -> list[str]:
    groups: dict[str, list[CellResult]] = {}
    for result in results:
        groups.setdefault(key(result), []).append(result)
    if drew:
        rows = ["| | frames READY | turns a frame | messages a frame | $ a frame | min a cell |",
                "| --- | --- | --- | --- | --- | --- |"]  # fmt: skip
    else:
        rows = ["| | planned | first answer usable | answers | frames | $ a plan | s a plan |",
                "| --- | --- | --- | --- | --- | --- | --- |"]  # fmt: skip
    for name, group in groups.items():
        frames = [f for r in group for f in r.frames]
        if drew:
            ready = sum(f.status == "READY" for f in frames)
            rows.append(
                f"| {name} | {ready} of {len(frames)} ({_share(ready, len(frames))}) "
                f"| {_mean(f.turns for f in frames):.1f} | {_mean(f.calls for f in frames):.1f} "
                f"| {sum(r.cost_usd for r in group) / max(len(frames), 1):.3f} "
                f"| {_mean(r.seconds for r in group) / 60:.1f} |"
            )
        else:
            planned = sum(r.planned for r in group)
            first = sum(r.planned and r.answers == 1 for r in group)
            rows.append(
                f"| {name} | {planned} of {len(group)} | {first} of {len(group)} "
                f"| {_mean(r.answers for r in group):.1f} "
                f"| {_mean(r.planned_frames for r in group):.1f} "
                f"| {_mean(r.cost_usd for r in group):.3f} "
                f"| {_mean(r.seconds for r in group):.0f} |"
            )
    return rows


def gallery(results: list[CellResult], title: str = "eval") -> str:
    """Every frame drawn, cell by cell, with its status: open it from the eval folder."""
    parts = [
        "<!doctype html>",
        '<meta charset="utf-8">',
        f"<title>{html.escape(title)}</title>",
        "<style>body{font:14px sans-serif;margin:16px;background:#fff;color:#111}"
        "figure{display:inline-block;margin:6px;vertical-align:top}"
        "img{max-width:360px;max-height:360px;border:1px solid #ccc}"
        ".bad{color:#b00}</style>",
        f"<h1>{html.escape(title)}</h1>",
    ]
    for r in results:
        head = f"{r.cell.id}: {r.cell.topic} ({r.cell.aspect}; {r.cell.planner} / {r.cell.agent})"
        parts.append(f"<h2>{html.escape(head)}</h2>")
        if r.error:
            parts.append(f'<p class="bad">{html.escape(r.error)}</p>')
        for f in r.frames:
            said = f"{f.frame}: {f.status}" + (f" ({', '.join(f.codes)})" if f.codes else "")
            mark = "" if f.status == "READY" else ' class="bad"'
            image = f'<img src="{html.escape(f.picture)}" alt="">' if f.picture else ""
            parts.append(
                f"<figure>{image}<figcaption{mark}>{html.escape(said)}</figcaption></figure>"
            )
    return "\n".join(parts) + "\n"


def _share(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "-"


def _mean(values: Iterable[float]) -> float:
    found = list(values)
    return mean(found) if found else 0.0
