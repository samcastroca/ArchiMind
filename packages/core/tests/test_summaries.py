import pytest
from archimind_core.summaries import count, truncate


@pytest.mark.parametrize(
    ("n", "singular", "plural", "expected"),
    [
        (1, "muro", None, "1 muro"),
        (0, "muro", None, "0 muros"),
        (2, "error", "errores", "2 errores"),
        (1, "nivel", "niveles", "1 nivel"),
    ],
)
def test_count_agrees_in_number(n: int, singular: str, plural: str | None, expected: str) -> None:
    assert count(n, singular, plural) == expected


def test_truncate_keeps_short_lists_and_says_how_many_are_left_out() -> None:
    lines = [f"línea {i}" for i in range(10)]
    assert truncate(lines, 10) == lines
    cut = truncate(lines, 4)
    assert cut == ["línea 0", "línea 1", "línea 2", "  … y 7 más"]
    assert len(cut) == 4
