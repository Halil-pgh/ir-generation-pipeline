"""pipeline.toml loading: valid files load, every mistake is a PipelineConfigError."""

from pathlib import Path

import pytest

from irpipe.core import PipelineConfigError, load_config

REPO_ROOT = Path(__file__).resolve().parents[2]


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "pipeline.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_valid_file_loads(tmp_path: Path) -> None:
    config = load_config(
        write(
            tmp_path,
            """
            [pipeline]
            stages = ["validate", "resolve"]
            plugins = ["irpipe.frontend"]

            [options.resolve]
            label_gap = 0.15
            """,
        )
    )
    assert config.pipeline.stages == ["validate", "resolve"]
    assert config.pipeline.plugins == ["irpipe.frontend"]
    assert config.options == {"resolve": {"label_gap": 0.15}}


def test_an_empty_file_means_an_empty_pipeline(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, ""))
    assert config.pipeline.stages == []
    assert config.options == {}


def test_a_misspelled_key_is_reported_with_its_path(tmp_path: Path) -> None:
    with pytest.raises(PipelineConfigError, match=r"pipeline\.stagse: Extra inputs"):
        load_config(write(tmp_path, '[pipeline]\nstagse = ["validate"]\n'))


def test_broken_toml_is_reported(tmp_path: Path) -> None:
    with pytest.raises(PipelineConfigError, match="not valid TOML"):
        load_config(write(tmp_path, "[pipeline\n"))


def test_a_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(PipelineConfigError, match="config file not found"):
        load_config(tmp_path / "nope.toml")


def test_the_repository_pipeline_toml_is_valid() -> None:
    load_config(REPO_ROOT / "pipeline.toml")
