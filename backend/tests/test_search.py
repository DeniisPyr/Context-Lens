import pytest

from context_lens.services.answering import Excerpt, not_found_answer
from context_lens.services.documents import Document
from context_lens.services.search import (
    DatasetAnswer,
    FoundChunk,
    excerpts_from_chunks,
    with_real_lines,
)


def chunk(
    position: int,
    start_line: int,
    end_line: int,
    text: str,
    document_id: str = "doc-a",
    filename: str = "a.txt",
) -> FoundChunk:
    return FoundChunk(
        document_id=document_id,
        filename=filename,
        position=position,
        start_line=start_line,
        end_line=end_line,
        text=text,
    )


def test_one_chunk_is_one_excerpt_of_its_lines() -> None:
    found = [chunk(0, 3, 5, "three\n\nfive")]

    assert excerpts_from_chunks(found) == [
        Excerpt(
            document_id="doc-a",
            filename="a.txt",
            lines={3: "three", 4: "", 5: "five"},
        )
    ]


def test_chunks_that_touch_are_merged_into_one_excerpt() -> None:
    found = [chunk(1, 3, 4, "three\nfour"), chunk(0, 1, 2, "one\ntwo")]

    assert excerpts_from_chunks(found) == [
        Excerpt(
            document_id="doc-a",
            filename="a.txt",
            lines={1: "one", 2: "two", 3: "three", 4: "four"},
        )
    ]


def test_chunks_with_lines_between_them_stay_apart_in_line_order() -> None:
    found = [chunk(2, 7, 7, "seven"), chunk(0, 1, 2, "one\ntwo")]

    assert excerpts_from_chunks(found) == [
        Excerpt(document_id="doc-a", filename="a.txt", lines={1: "one", 2: "two"}),
        Excerpt(document_id="doc-a", filename="a.txt", lines={7: "seven"}),
    ]


def test_documents_come_in_the_order_of_their_nearest_chunk() -> None:
    found = [
        chunk(4, 9, 9, "b nine", "doc-b", "b.md"),
        chunk(0, 1, 1, "a one"),
        chunk(0, 2, 2, "b two", "doc-b", "b.md"),
        chunk(3, 8, 8, "a eight"),
    ]

    assert excerpts_from_chunks(found) == [
        Excerpt(document_id="doc-b", filename="b.md", lines={2: "b two"}),
        Excerpt(document_id="doc-b", filename="b.md", lines={9: "b nine"}),
        Excerpt(document_id="doc-a", filename="a.txt", lines={1: "a one"}),
        Excerpt(document_id="doc-a", filename="a.txt", lines={8: "a eight"}),
    ]


def test_pieces_of_a_long_line_are_joined_with_a_space_in_their_order() -> None:
    found = [
        chunk(3, 2, 2, "third piece"),
        chunk(1, 2, 2, "first piece"),
        chunk(2, 2, 2, "second piece"),
    ]

    assert excerpts_from_chunks(found) == [
        Excerpt(
            document_id="doc-a",
            filename="a.txt",
            lines={2: "first piece second piece third piece"},
        )
    ]


def test_a_piece_of_a_long_line_merges_with_the_lines_around_it() -> None:
    found = [
        chunk(0, 1, 1, "before"),
        chunk(2, 2, 2, "end of the long line"),
        chunk(3, 3, 4, "after\nand more"),
    ]

    assert excerpts_from_chunks(found) == [
        Excerpt(
            document_id="doc-a",
            filename="a.txt",
            lines={
                1: "before",
                2: "end of the long line",
                3: "after",
                4: "and more",
            },
        )
    ]


def test_no_chunks_make_no_excerpts() -> None:
    assert excerpts_from_chunks([]) == []


def test_real_lines_replace_the_lines_shown_but_keep_their_numbers() -> None:
    document = Document(
        id="doc-a", filename="a.txt", text="one\ntwo  pieces\nthree\nfour\n"
    )
    shown = [
        Excerpt(document_id="doc-a", filename="a.txt", lines={2: "two pieces"}),
        Excerpt(document_id="doc-a", filename="a.txt", lines={4: "four"}),
    ]

    assert with_real_lines(shown, [document]) == [
        Excerpt(document_id="doc-a", filename="a.txt", lines={2: "two  pieces"}),
        Excerpt(document_id="doc-a", filename="a.txt", lines={4: "four"}),
    ]


def test_excerpts_of_a_document_not_loaded_are_left_out() -> None:
    document = Document(id="doc-b", filename="b.md", text="b one\n")
    shown = [
        Excerpt(document_id="doc-a", filename="a.txt", lines={1: "a one"}),
        Excerpt(document_id="doc-b", filename="b.md", lines={1: "b one"}),
    ]

    assert with_real_lines(shown, [document]) == [
        Excerpt(document_id="doc-b", filename="b.md", lines={1: "b one"})
    ]


@pytest.mark.parametrize(
    ("line", "page"),
    [(1, 1), (4, 1), (5, 3), (7, 3), (8, 4), (9, 4)],
)
def test_line_is_on_the_last_page_that_starts_before_it_or_on_it(
    line: int, page: int
) -> None:
    # Pages of 4, 0, 3 and 2 lines: the second page has none, so it's never the one.
    answer = DatasetAnswer(
        answer=not_found_answer(), excerpts=[], page_starts={"doc-a": (1, 5, 5, 8)}
    )

    assert answer.page_of("doc-a", line) == page


def test_line_of_a_document_without_page_starts_is_on_no_page() -> None:
    answer = DatasetAnswer(
        answer=not_found_answer(), excerpts=[], page_starts={"doc-a": (1, 3)}
    )

    assert answer.page_of("doc-b", 1) is None
