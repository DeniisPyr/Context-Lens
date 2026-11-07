import random
from itertools import pairwise
from pathlib import Path

import pytest

from context_lens.services.chunking import (
    MAX_CHUNK_CHARACTERS,
    MAX_HEADING_CHARACTERS,
    TextChunk,
    split_into_chunks,
)
from context_lens.services.documents import split_lines

DOCUMENTS = Path(__file__).resolve().parents[1] / "evals" / "documents"
MAX = MAX_CHUNK_CHARACTERS
HEADING = MAX_HEADING_CHARACTERS


def line_of(character: str, length: int) -> str:
    return character * length


def is_piece_of_a_long_line(chunk: TextChunk, lines: list[str]) -> bool:
    line = lines[chunk.start_line - 1]
    return chunk.start_line == chunk.end_line and len(line) > MAX


def assert_chunks_fit_their_lines(lines: list[str], chunks: list[TextChunk]) -> None:
    for chunk in chunks:
        assert 1 <= chunk.start_line <= chunk.end_line <= len(lines)
        assert chunk.text.strip()
        assert len(chunk.text) <= MAX
        if is_piece_of_a_long_line(chunk, lines):
            assert chunk.text in lines[chunk.start_line - 1]
        else:
            assert chunk.text == "\n".join(lines[chunk.start_line - 1 : chunk.end_line])
            # Trimmed, so that the line range starts and ends on text.
            assert lines[chunk.start_line - 1].strip()
            assert lines[chunk.end_line - 1].strip()
    for before, after in pairwise(chunks):
        pieces_of_one_line = before.start_line == after.end_line
        assert before.end_line < after.start_line or pieces_of_one_line
    covered = {
        number
        for chunk in chunks
        for number in range(chunk.start_line, chunk.end_line + 1)
    }
    for number, line in enumerate(lines, start=1):
        assert number in covered or not line.strip()


def without_whitespace(text: str) -> str:
    return "".join(text.split())


def assert_pieces_hold_the_whole_line(line: str, chunks: list[TextChunk]) -> None:
    assert "".join(without_whitespace(chunk.text) for chunk in chunks) == (
        without_whitespace(line)
    )


def test_short_document_is_one_chunk() -> None:
    lines = ["# Notes", "", "The cat is orange.", "The dog is brown."]

    assert split_into_chunks(lines) == [
        TextChunk(1, 4, "# Notes\n\nThe cat is orange.\nThe dog is brown.")
    ]


@pytest.mark.parametrize(
    "lines",
    [
        pytest.param([], id="no_lines"),
        pytest.param([""], id="one_empty_line"),
        pytest.param(["", " ", "\t", " "], id="only_whitespace"),
        pytest.param(["", line_of(" ", 3 * MAX), ""], id="long_line_of_spaces"),
    ],
)
def test_document_without_text_has_no_chunks(lines: list[str]) -> None:
    assert split_into_chunks(lines) == []


def test_blank_lines_are_trimmed_off_both_ends() -> None:
    lines = ["", "  ", "first", "", "second", "\t", ""]

    assert split_into_chunks(lines) == [TextChunk(3, 5, "first\n\nsecond")]


def test_lines_are_kept_exactly_as_they_are() -> None:
    lines = ["  indented", "\ttab", "trailing  ", "form\x0cfeed"]

    [chunk] = split_into_chunks(lines)

    assert chunk.text == "  indented\n\ttab\ntrailing  \nform\x0cfeed"


def test_chunk_fills_up_to_the_maximum_counting_the_line_breaks() -> None:
    # Exactly the maximum, with the line break between them.
    lines = [line_of("a", MAX // 2 - 1), line_of("b", MAX - MAX // 2)]

    assert split_into_chunks(lines) == [TextChunk(1, 2, "\n".join(lines))]


def test_line_that_does_not_fit_starts_the_next_chunk() -> None:
    # One character over the maximum, which only the line break between them makes.
    lines = [line_of("a", MAX // 2), line_of("b", MAX - MAX // 2)]

    assert split_into_chunks(lines) == [
        TextChunk(1, 1, lines[0]),
        TextChunk(2, 2, lines[1]),
    ]


def test_chunk_without_blank_lines_ends_before_the_line_that_does_not_fit() -> None:
    # Three of these lines fit in a chunk, and a fourth doesn't.
    lines = [line_of(str(number), MAX // 3 - 1) for number in range(8)]

    chunks = split_into_chunks(lines)

    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [
        (1, 3),
        (4, 6),
        (7, 8),
    ]


def test_chunk_ends_at_its_last_blank_line_to_keep_the_next_paragraph_whole() -> None:
    # Four of these lines and the blank one fit in a chunk, and the fifth doesn't.
    length = MAX // 5
    first = [line_of("a", length), line_of("b", length)]
    second = [line_of("c", length), line_of("d", length)]
    lines = [*first, "", *second, line_of("e", length)]

    chunks = split_into_chunks(lines)

    assert chunks == [
        TextChunk(1, 2, "\n".join(first)),
        TextChunk(4, 6, "\n".join([*second, lines[5]])),
    ]


def test_chunk_ends_at_the_last_of_several_blank_lines() -> None:
    # All but the last line fit in a chunk, with two blank lines past its first third.
    short, long = MAX // 10, MAX // 4
    lines = [
        line_of("a", short),
        "",
        line_of("b", long),
        "",
        line_of("c", long),
        "",
        line_of("d", long),
        line_of("e", long),
    ]

    chunks = split_into_chunks(lines)

    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [(1, 5), (7, 8)]


def test_blank_line_in_the_first_third_does_not_end_the_chunk() -> None:
    # Ending there would leave a chunk a tenth of the maximum long.
    lines = [
        line_of("a", MAX // 10),
        "",
        line_of("b", MAX * 2 // 3),
        line_of("c", MAX // 2),
    ]
    # Proves the blank line is in the first third of the chunk that doesn't fit c.
    assert len(lines[0]) + 1 < len("\n".join(lines[:3])) / 3

    chunks = split_into_chunks(lines)

    assert chunks == [
        TextChunk(1, 3, "\n".join(lines[:3])),
        TextChunk(4, 4, lines[3]),
    ]


HEADING_CASES = [
    pytest.param(
        [line_of("H", HEADING)], [(1, 3), (5, 7)], id="heading_moves_to_the_next_chunk"
    ),
    pytest.param(
        [line_of("H", HEADING + 1)], [(1, 5), (7, 7)], id="longer_line_is_not_a_heading"
    ),
    pytest.param(
        ["## 5. Sick leave", "", "### 5.1 Reporting"],
        [(1, 3), (5, 9)],
        id="stacked_headings_move_together",
    ),
    pytest.param(
        ["8. DAILY MAINTENANCE", "=" * 20],
        [(1, 3), (5, 8)],
        id="underlined_heading_moves_whole",
    ),
    pytest.param(
        ["- one", "- two", "- three"],
        [(1, 7), (9, 9)],
        id="three_short_lines_are_not_a_heading",
    ),
    pytest.param(
        [line_of("x", MAX // 5), "End of x."],
        [(1, 6), (8, 8)],
        id="short_last_line_of_a_paragraph_stays",
    ),
]


@pytest.mark.parametrize(("heading", "expected"), HEADING_CASES)
def test_headings_before_the_end_go_with_the_text_after_them(
    heading: list[str], expected: list[tuple[int, int]]
) -> None:
    # Everything up to the blank line before c fits in a chunk, and c doesn't.
    lines = [
        line_of("a", MAX * 2 // 5),
        "",
        line_of("b", MAX // 3),
        "",
        *heading,
        "",
        line_of("c", MAX // 3),
    ]

    chunks = split_into_chunks(lines)

    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == expected
    assert_chunks_fit_their_lines(lines, chunks)


def test_heading_that_starts_the_chunk_keeps_its_text() -> None:
    # The blank line after the heading is past the first third of the chunk, but ending
    # there would leave the heading alone.
    lines = [
        line_of("H", HEADING),
        "",
        line_of("b", HEADING),
        line_of("c", MAX - HEADING),
    ]

    chunks = split_into_chunks(lines)

    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [(1, 3), (4, 4)]


def test_list_entries_separated_by_blank_lines_stay_whole() -> None:
    entries = [
        [f"E-{number:03d} Pump pressure too high", f"Cause: {'x' * 150}", "Fix: y"]
        for number in range(MAX // 50)
    ]
    lines = [line for entry in entries for line in [*entry, ""]]

    chunks = split_into_chunks(lines)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.text.startswith("E-")
        assert chunk.text.endswith("Fix: y")
    assert_chunks_fit_their_lines(lines, chunks)


def test_long_line_is_split_at_whitespace_into_pieces_of_that_line() -> None:
    line = " ".join(f"slovo{number}" for number in range(MAX // 2))
    lines = ["before", line, "after"]

    chunks = split_into_chunks(lines)

    [before, *pieces, after] = chunks
    assert before == TextChunk(1, 1, "before")
    assert after == TextChunk(3, 3, "after")
    assert len(pieces) > 1
    for piece in pieces:
        assert (piece.start_line, piece.end_line) == (2, 2)
        assert piece.text == piece.text.strip()
        assert all(word.startswith("slovo") for word in piece.text.split(" "))
    assert " ".join(piece.text for piece in pieces) == line
    assert_chunks_fit_their_lines(lines, chunks)


def test_long_line_without_whitespace_is_split_at_the_maximum() -> None:
    line = line_of("x", 2 * MAX + 200)

    chunks = split_into_chunks([line])

    assert chunks == [
        TextChunk(1, 1, line_of("x", MAX)),
        TextChunk(1, 1, line_of("x", MAX)),
        TextChunk(1, 1, line_of("x", 200)),
    ]


def test_long_line_ends_the_chunk_before_it() -> None:
    lines = [line_of("a", MAX // 5), "", line_of("b", MAX // 5), line_of("c", MAX + 1)]

    chunks = split_into_chunks(lines)

    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [
        (1, 1),
        (3, 3),
        (4, 4),
        (4, 4),
    ]
    assert_pieces_hold_the_whole_line(lines[3], chunks[2:])


def test_line_of_exactly_the_maximum_is_not_split() -> None:
    line = line_of("x", MAX)

    assert split_into_chunks([line]) == [TextChunk(1, 1, line)]


def test_czech_text_is_counted_in_characters_not_bytes() -> None:
    # Each "ž" is two bytes in UTF-8.
    fits = line_of("ž", MAX)
    too_long = line_of("ž", MAX + 1)

    assert split_into_chunks([fits]) == [TextChunk(1, 1, fits)]
    assert [chunk.text for chunk in split_into_chunks([too_long])] == [fits, "ž"]


def test_czech_document_keeps_its_line_numbers() -> None:
    lines = ["Cestovní náhrady", "", "Příliš žluťoučký kůň úpěl ďábelské ódy."] * 60

    chunks = split_into_chunks(lines)

    assert len(chunks) > 1
    assert_chunks_fit_their_lines(lines, chunks)


@pytest.mark.parametrize("seed", range(5))
def test_random_documents_keep_every_rule(seed: int) -> None:
    # Lines of every kind, in a fixed but arbitrary order.
    generator = random.Random(seed)
    for _ in range(40):
        lines = [
            generator.choice(
                [
                    "",
                    " ",
                    "slovo " * generator.randint(1, 60),
                    "x" * generator.randint(1, MAX // 2),
                    "slovo " * generator.randint(MAX // 6, MAX // 2),
                    "y" * generator.randint(MAX - 10, 2 * MAX + 10),
                ]
            )
            for _ in range(generator.randint(0, 60))
        ]

        chunks = split_into_chunks(lines)

        assert_chunks_fit_their_lines(lines, chunks)
        for number, line in enumerate(lines, start=1):
            if len(line) > MAX:
                pieces = [chunk for chunk in chunks if chunk.start_line == number]
                assert_pieces_hold_the_whole_line(line, pieces)


@pytest.mark.parametrize(
    "path", sorted(DOCUMENTS.iterdir()), ids=lambda path: path.name
)
def test_evaluation_documents_keep_every_rule(path: Path) -> None:
    lines = split_lines(path.read_text(encoding="utf-8"))

    chunks = split_into_chunks(lines)

    assert len(chunks) > 1
    assert_chunks_fit_their_lines(lines, chunks)
    # Whole lines only: none of these documents has a line over the maximum.
    assert not any(is_piece_of_a_long_line(chunk, lines) for chunk in chunks)
