from pathlib import Path

import pytest

from job_market.config import find_project_root, load_settings


def test_root_is_found_from_a_subfolder(mini_project):
    nested = mini_project.root / "notebooks" / "deeper"
    nested.mkdir(parents=True)
    assert find_project_root(nested) == mini_project.root


def test_environment_variable_overrides_the_search(mini_project, monkeypatch, tmp_path):
    monkeypatch.setenv("JOB_MARKET_ROOT", str(mini_project.root))
    assert find_project_root(Path("/")) == mini_project.root


def test_missing_config_gives_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("JOB_MARKET_ROOT", raising=False)
    with pytest.raises(FileNotFoundError, match="pipeline.toml"):
        find_project_root(tmp_path)


def test_config_hash_ignores_line_endings(mini_project):
    config = mini_project.root / "config" / "pipeline.toml"
    lf_hash = load_settings(mini_project.root).config_sha256
    config.write_bytes(config.read_bytes().replace(b"\n", b"\r\n"))
    assert load_settings(mini_project.root).config_sha256 == lf_hash


def test_missing_section_names_the_section(mini_project):
    with pytest.raises(KeyError, match="nonexistent"):
        mini_project.section("nonexistent")


def test_paths_resolve_inside_the_project(mini_project):
    assert mini_project.root in mini_project.path("processed_dir").parents
