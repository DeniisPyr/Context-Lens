import pytest

from context_lens.services.embeddings import query_embedding_text


@pytest.mark.parametrize(
    ("question", "text"),
    [
        pytest.param(
            "How many days off?",
            "task: search result | query: How many days off?",
            id="english",
        ),
        pytest.param(
            "Kolik je stravné?",
            "task: search result | query: Kolik je stravné?",
            id="czech",
        ),
    ],
)
def test_question_is_embedded_in_googles_format_for_search_queries(
    question: str, text: str
) -> None:
    assert query_embedding_text(question) == text
