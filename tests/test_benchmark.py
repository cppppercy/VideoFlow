import pytest

from videoflow.benchmark import (
    _parse_configurations,
    character_error_rate,
    normalize_cer_text,
)


def test_character_error_rate_ignores_layout_whitespace() -> None:
    assert normalize_cer_text("机器 学习\n课程") == "机器学习课程"
    assert character_error_rate("机器学习课程", "机器 学习\n课程") == 0.0


def test_character_error_rate_counts_substitution() -> None:
    assert character_error_rate("机器学习", "机器学期") == pytest.approx(0.25)


def test_benchmark_configuration_parser_keeps_profiles_and_raw_models() -> None:
    assert _parse_configurations("fast,balanced", "small") == [
        ("fast", "base", "fast"),
        ("balanced", "base", "balanced"),
        ("model-small", "small", None),
    ]
