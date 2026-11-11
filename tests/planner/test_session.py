"""The planner with a scripted model: a lesson planned into its folder, answers sent back,
a frame shortened or split, and the records."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from irpipe.cli import main
from irpipe.orchestrator.inputs import read_inputs
from irpipe.planner import PlannerError, Wishes, plan, revise
from irpipe.schema.request import PlannerRequest

type Config = Callable[..., Path]


def records(folder: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((folder / "planner" / "session.json").read_text())
    return data


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_a_plan_fills_the_lesson_folder_with_what_the_agent_draws_from(
    tmp_path: Path, planner_config: Config, scripted: Callable[..., Any], kit: Any
) -> None:
    client = scripted(kit.THREE)
    folder = tmp_path / "lesson"
    result = plan("vector projection", folder, config_path=planner_config(), client=client)
    assert names(folder) == [
        "lesson_plan.json", "planner", "projection.brief.json", "recap.brief.json",
        "two_vectors.brief.json",
    ]  # fmt: skip
    assert list(result.briefs) == ["two_vectors", "projection", "recap"]
    assert result.changed == ("two_vectors", "projection", "recap")
    assert result.answers == 1 and result.cost_usd == pytest.approx(0.01)
    inputs, issues = read_inputs(result.briefs["recap"])  # lesson_plan.json beside it
    assert issues == [] and inputs is not None and inputs.lesson == result.lesson
    system = (folder / "planner" / "system_prompt.md").read_text()
    assert system == client.systems[0]
    assert '"title":"LessonPlan"' in system and '"title":"FrameBrief"' in system  # schemas
    assert "tiktok (TikTok, full screen, 9:16 only)" in system  # what the project offers
    assert '"id": "vector_projection"' in system  # the example
    first = client.sent[0][0].text
    assert "<topic>\nvector projection\n</topic>" in first and "The user asks" not in first
    assert names(folder / "planner" / "answers" / "1") == [
        "answer.md", "lesson_plan.json", "projection.brief.json", "recap.brief.json",
        "two_vectors.brief.json",
    ]  # fmt: skip
    session = records(folder)
    assert session["sessions"] == [
        {"kind": "plan", "topic": "vector projection", "answers": [{"answer": 1, "problems": []}],
         "cost_usd": 0.01, "ended": "answer 1 is used"},
    ]  # fmt: skip
    assert session["settings"]["model"] == "claude-sonnet-5-5"


def test_an_answer_with_problems_goes_back_with_them_and_the_next_is_used(
    tmp_path: Path, planner_config: Config, scripted: Callable[..., Any], kit: Any
) -> None:
    wrong = kit.answer(
        kit.lesson(("projection", "define"), ("recap", "summary")), [kit.brief(focus=["x"])]
    )
    client = scripted("I think the lesson should be short.", wrong, kit.ONE)
    folder = tmp_path / "lesson"
    result = plan("projection", folder, config_path=planner_config(), client=client)
    assert result.answers == 3 and list(result.briefs) == ["projection"]
    back = client.sent[1][-1].text
    assert back.startswith("Your answer cannot be used yet; nothing of it was kept:\n- the answer")
    problems = [a["problems"] for a in records(folder)["sessions"][0]["answers"]]
    assert [len(p) for p in problems] == [1, 2, 0]  # a brief that cannot be read is there
    assert any("focus names 'x'" in p for p in problems[1])
    assert any("'recap' of the lesson plan has no brief" in p for p in problems[1])
    assert names(folder / "planner" / "answers") == ["1", "2", "3"]
    transcript = (folder / "planner" / "transcript.md").read_text()
    assert transcript.count("## assistant") == 3 and transcript.count("## user") == 3


def test_without_a_usable_answer_the_planner_fails_and_keeps_its_records(
    tmp_path: Path, planner_config: Config, scripted: Callable[..., Any], kit: Any
) -> None:
    folder = tmp_path / "lesson"
    with pytest.raises(PlannerError, match="no usable answer in 2"):
        plan("x", folder, config_path=planner_config(max_answers=2), client=scripted("no", "no"))
    assert records(folder)["sessions"][0]["ended"] == "no usable answer in 2"
    assert not (folder / "lesson_plan.json").exists()
    with pytest.raises(PlannerError, match="could not answer: the network is down"):
        down = scripted(kit.LLMError("the network is down"))
        plan("x", folder, config_path=planner_config(), client=down)


def test_the_users_wishes_are_told_and_win_over_the_planners_choice(
    tmp_path: Path, planner_config: Config, scripted: Callable[..., Any], kit: Any
) -> None:
    sideways = kit.answer(
        kit.lesson(("projection", "define")), [kit.brief(render_profile={"aspect": "16:9"})]
    )
    client = scripted(sideways)
    wishes = Wishes(frames=1, aspect="9:16", lang="tr")
    result = plan("x", tmp_path / "l", wishes=wishes, config_path=planner_config(), client=client)
    assert (
        "The user asks for exactly 1 frame; the aspect 9:16; every text of the pictures in "
        "the language 'tr'. This is not yours to change." in client.sent[0][0].text
    )
    inputs, _ = read_inputs(result.briefs["projection"])
    assert inputs is not None
    assert inputs.style.render_profile.aspect == "9:16"
    assert inputs.style.render_profile.typography.lang == "tr"
    assert inputs.header.frame.units[0] < inputs.header.frame.units[1]  # portrait
    assert records(tmp_path / "l")["wishes"] == {"frames": 1, "aspect": "9:16", "lang": "tr"}


def test_a_shortened_frame_keeps_its_id_and_the_other_briefs_stay(
    tmp_path: Path, planner_config: Config, scripted: Callable[..., Any], kit: Any
) -> None:
    folder, config = tmp_path / "lesson", planner_config()
    plan("x", folder, config_path=config, client=scripted(kit.THREE))
    recap = (folder / "recap.brief.json").read_text()
    shorter = kit.brief(must_show=kit.BRIEF["must_show"][:3], focus=[])
    plan_three = json.loads((folder / "lesson_plan.json").read_text())
    client = scripted(kit.answer(plan_three, [shorter]))
    request = PlannerRequest(
        frame="projection", kind="shorten", reason="the formula does not fit", items=("formula",)
    )
    result = revise(request, folder, config_path=config, client=client)
    assert result.changed == ("projection",) and list(result.briefs) == [
        "two_vectors", "projection", "recap",
    ]  # fmt: skip
    written = json.loads((folder / "projection.brief.json").read_text())
    assert [item["id"] for item in written["must_show"]] == ["vectors", "shadow", "drop"]
    assert (folder / "recap.brief.json").read_text() == recap
    first = client.sent[0][0].text
    assert first.startswith("Frame 'projection' cannot be drawn as its brief asks")
    assert '"kind": "shorten"' in first and "<lesson_plan>" in first and "<brief>" in first
    sessions = records(folder)["sessions"]
    assert [s["kind"] for s in sessions] == ["plan", "shorten"]
    assert sessions[1]["request"]["items"] == ["formula"]
    assert names(folder / "planner" / "answers") == ["1", "2"]


def test_a_split_frame_gives_way_to_two_and_its_brief_is_removed(
    tmp_path: Path, planner_config: Config, scripted: Callable[..., Any], kit: Any
) -> None:
    folder, config = tmp_path / "lesson", planner_config()
    plan("x", folder, config_path=config, client=scripted(kit.THREE))
    frames = [("two_vectors", "introduce"), ("shadow", "define"), ("formula", "example"),
              ("recap", "summary")]  # fmt: skip
    in_place = kit.answer(
        kit.lesson(*frames), [kit.brief("shadow"), kit.brief("formula", "example")]
    )
    still_there = kit.answer(kit.lesson(("two_vectors", "introduce"), ("projection", "define"),
                                        ("recap", "summary")), [kit.brief()])  # fmt: skip
    client = scripted(still_there, in_place)
    request = PlannerRequest(frame="projection", kind="split", reason="two ideas in one frame")
    result = revise(request, folder, config_path=config, client=client)
    assert "frame 'projection' is split" in client.sent[1][-1].text
    assert list(result.briefs) == ["two_vectors", "shadow", "formula", "recap"]
    assert result.changed == ("shadow", "formula")
    assert names(folder) == [
        "formula.brief.json", "lesson_plan.json", "planner", "recap.brief.json",
        "shadow.brief.json", "two_vectors.brief.json",
    ]  # fmt: skip


def test_a_revision_needs_the_lesson_and_the_frame(tmp_path: Path, planner_config: Config) -> None:
    request = PlannerRequest(frame="projection", kind="fix", reason="E-BRIEF")
    with pytest.raises(PlannerError, match="holds no lesson with a frame 'projection'"):
        revise(request, tmp_path, config_path=planner_config())


def test_the_plan_command_prints_the_frames_and_the_files(
    tmp_path: Path,
    planner_config: Config,
    scripted: Callable[..., Any],
    kit: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = scripted(kit.THREE)
    monkeypatch.setattr("irpipe.planner.session.LLM_CLIENTS.get", lambda name: lambda s: client)
    out = tmp_path / "lesson"
    config = str(planner_config())
    assert main(["plan", "Vektör izdüşümü", "-o", str(out), "--config", config]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed[0] == "lesson 'vector_projection': 3 frames (1 answer, $0.0100)"
    assert printed[1] == "  two_vectors (introduce): the frame two_vectors"
    assert printed[-1] == f"  -> {out / 'recap.brief.json'}"
    assert main(["plan", "x", "--platform", "tiktk", "--config", config]) == 2
    assert "did you mean 'tiktok'?" in capsys.readouterr().err


@pytest.mark.llm
def test_the_planner_plans_a_lesson_the_orchestrator_reads_with_the_real_model(
    tmp_path: Path,
) -> None:
    config = Path(__file__).parent.parent.parent / "pipeline.toml"
    wishes = Wishes(frames=3)
    result = plan("projecting one vector onto another", tmp_path, wishes=wishes, config_path=config)
    assert len(result.briefs) == 3 and result.answers <= 3
    for path in result.briefs.values():
        assert read_inputs(path)[1] == []
