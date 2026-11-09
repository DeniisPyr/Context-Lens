import json
import re
from pathlib import Path

import pytest

from context_lens.evaluation.cases import (
    InvalidQuestionSetError,
    LineRange,
    Question,
    QuestionSet,
    load_question_set,
    select_questions,
)

HANDBOOK = (
    "# Handbook\n"
    "Employees can work from home 3 days a week.\n"
    "The office opens at 8:00.\n"
)
REMOTE_DAYS = {
    "id": "handbook-remote-days",
    "document": "handbook.md",
    "category": "fact",
    "question": "How many days a week can employees work from home?",
    "facts": [["3 days", "three days"]],
    "evidence": [[2, 2]],
}
PARKING = {
    "id": "handbook-parking",
    "document": "handbook.md",
    "category": "missing_related",
    "question": "Where can employees park?",
}
RULES = "# Rules\nDress well.\nNo dogs in the lab.\n"
TWO_DOCUMENTS = {"handbook.md": HANDBOOK.encode(), "rules.md": RULES.encode()}
REMOTE_DAYS_AND_DRESS = {
    "id": "handbook-remote-days-and-dress",
    "document": "handbook.md",
    "category": "cross_document",
    "question": "How many days a week can employees work from home, and how to dress?",
    "facts": [["3 days"], ["dress well"]],
    "evidence": [[2, 2], ["rules.md", 2, 2]],
}
# Each office opens at its own time, so the question can't be answered until the user
# says which office they mean. The handbook has an opening time too.
OFFICES = "# Offices\nPrague opens at 8:00.\nBrno opens at 9:00.\n"
WITH_OFFICES = {"handbook.md": HANDBOOK.encode(), "offices.md": OFFICES.encode()}
OPENING_TIME = {
    "id": "offices-opening-time",
    "document": "offices.md",
    "category": "clarify",
    "question": "When does the office open?",
    "reply": "I work in Brno.",
    "facts": [["9:00", "nine"]],
    "evidence": [[3, 3]],
    "cases": [[2, 3], ["handbook.md", 3, 3]],
}


def without(question: dict[str, object], key: str) -> dict[str, object]:
    return {name: value for name, value in question.items() if name != key}


def as_toml(*questions: dict[str, object]) -> str:
    # JSON's strings, numbers and arrays are valid TOML values too.
    return "".join(
        "[[questions]]\n"
        + "".join(f"{key} = {json.dumps(value)}\n" for key, value in question.items())
        + "\n"
        for question in questions
    )


def write_set(
    folder: Path,
    questions_toml: str | bytes,
    documents: dict[str, bytes] | None = None,
) -> Path:
    if documents is None:
        documents = {"handbook.md": HANDBOOK.encode()}
    (folder / "documents").mkdir(parents=True)
    if isinstance(questions_toml, str):
        questions_toml = questions_toml.encode()
    (folder / "questions.toml").write_bytes(questions_toml)
    for name, data in documents.items():
        (folder / "documents" / name).write_bytes(data)
    return folder


def load_error(folder: Path) -> str:
    with pytest.raises(InvalidQuestionSetError) as error:
        load_question_set(folder)
    return str(error.value)


def test_question_set_has_its_questions_and_documents(tmp_path: Path) -> None:
    folder = write_set(tmp_path / "evals", as_toml(REMOTE_DAYS, PARKING))

    question_set = load_question_set(folder)

    assert question_set.questions == [
        Question.model_validate(REMOTE_DAYS),
        Question.model_validate(PARKING),
    ]
    assert list(question_set.documents) == ["handbook.md"]
    document = question_set.documents["handbook.md"]
    assert document.filename == "handbook.md"
    assert document.text == HANDBOOK
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", question_set.fingerprint)


def test_same_files_give_the_same_fingerprint(tmp_path: Path) -> None:
    first = load_question_set(write_set(tmp_path / "a", as_toml(REMOTE_DAYS)))
    second = load_question_set(write_set(tmp_path / "b", as_toml(REMOTE_DAYS)))

    assert first.fingerprint == second.fingerprint


@pytest.mark.parametrize(
    ("questions_toml", "documents"),
    [
        pytest.param(
            "# Edited.\n" + as_toml(REMOTE_DAYS), None, id="questions_file_changed"
        ),
        pytest.param(
            as_toml(REMOTE_DAYS),
            {"handbook.md": HANDBOOK.encode() + b"More text.\n"},
            id="document_changed",
        ),
        pytest.param(
            as_toml(REMOTE_DAYS),
            {"handbook.md": HANDBOOK.replace("\n", "\r\n").encode()},
            id="same_text_with_other_line_endings",
        ),
        pytest.param(
            as_toml(REMOTE_DAYS | {"document": "rules.md"}),
            {"rules.md": HANDBOOK.encode()},
            id="document_renamed",
        ),
        pytest.param(
            as_toml(REMOTE_DAYS),
            {"handbook.md": HANDBOOK.encode(), "rules.md": b"Dress well.\n"},
            id="document_no_question_is_about_added",
        ),
    ],
)
def test_any_change_to_the_files_changes_the_fingerprint(
    tmp_path: Path, questions_toml: str, documents: dict[str, bytes] | None
) -> None:
    original = write_set(tmp_path / "original", as_toml(REMOTE_DAYS))
    changed = write_set(tmp_path / "changed", questions_toml, documents)

    first = load_question_set(original)
    second = load_question_set(changed)

    assert first.fingerprint != second.fingerprint


def test_documents_no_question_is_about_are_in_the_set_too(tmp_path: Path) -> None:
    documents = {"rules.md": b"Dress well.\n", "handbook.md": HANDBOOK.encode()}
    folder = write_set(tmp_path / "evals", as_toml(REMOTE_DAYS), documents)

    question_set = load_question_set(folder)

    assert list(question_set.documents) == ["handbook.md", "rules.md"]
    assert question_set.documents["rules.md"].text == "Dress well.\n"


def test_hidden_files_are_left_out(tmp_path: Path) -> None:
    plain = write_set(tmp_path / "plain", as_toml(REMOTE_DAYS))
    documents = {
        "handbook.md": HANDBOOK.encode(),
        ".DS_Store": b"\x00\x01\xff",
        ".draft.md": b"Not ready.\n",
    }
    cluttered = write_set(tmp_path / "cluttered", as_toml(REMOTE_DAYS), documents)

    first = load_question_set(plain)
    second = load_question_set(cluttered)

    assert list(second.documents) == ["handbook.md"]
    assert first.fingerprint == second.fingerprint


def test_question_about_a_hidden_file_is_an_error(tmp_path: Path) -> None:
    question = PARKING | {"document": ".draft.md"}
    documents = {"handbook.md": HANDBOOK.encode(), ".draft.md": b"Not ready.\n"}
    folder = write_set(tmp_path / "evals", as_toml(question), documents)

    error = load_error(folder)

    assert error == (
        f"Question handbook-parking: .draft.md is not in {folder / 'documents'}."
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param({"id": "Handbook-Remote"}, "lowercase", id="uppercase_id"),
        pytest.param({"id": "handbook_remote"}, "lowercase", id="underscore_in_id"),
        pytest.param({"id": "handbook remote"}, "lowercase", id="space_in_id"),
        pytest.param({"evidnce": [[2, 2]]}, "evidnce: Extra inputs", id="unknown_key"),
        pytest.param({"category": "opinion"}, "category: Input", id="unknown_category"),
        pytest.param({"question": " "}, "question: String", id="blank_question"),
        pytest.param({"facts": "3 days"}, "facts: Input", id="facts_not_a_list"),
        pytest.param(
            {"evidence": [[2]]},
            "evidence: entry 1 must be [start, end] or [file, start, end]",
            id="evidence_not_a_pair",
        ),
        pytest.param(
            {"evidence": [[2, 2], [2, 2, 2]]},
            "evidence: entry 2 must be [start, end] or [file, start, end]",
            id="evidence_of_three_numbers",
        ),
        pytest.param(
            {"evidence": [["handbook.md", 2]]},
            "evidence: entry 1 must be [start, end] or [file, start, end]",
            id="evidence_file_without_an_end",
        ),
        pytest.param({"evidence": "2-2"}, "evidence: Input", id="evidence_not_a_list"),
        pytest.param({"facts": []}, "a fact question needs facts", id="no_facts"),
        pytest.param({"facts": [[]]}, "at least one phrasing", id="empty_fact"),
        pytest.param(
            {"facts": [["3 days", " "]]}, "must not be empty", id="blank_phrasing"
        ),
        pytest.param({"forbidden": [""]}, "must not be empty", id="empty_forbidden"),
        pytest.param({"evidence": []}, "needs evidence", id="no_evidence"),
        pytest.param(
            {"category": "missing_related"},
            "a missing_related question can't have facts or evidence",
            id="unanswerable_with_facts",
        ),
        pytest.param(
            {"category": "missing_unrelated", "facts": []},
            "a missing_unrelated question can't have facts or evidence",
            id="unanswerable_with_evidence",
        ),
        pytest.param(
            {"document": "missing.md"}, "missing.md is not in", id="no_such_document"
        ),
        pytest.param(
            {"evidence": [[3, 2]]}, "ends before it starts", id="evidence_backwards"
        ),
        pytest.param(
            {"evidence": [[0, 2]]},
            "outside handbook.md, which has 3 lines",
            id="evidence_from_line_zero",
        ),
        pytest.param(
            {"evidence": [[3, 4]]},
            "outside handbook.md, which has 3 lines",
            id="evidence_past_the_end",
        ),
        pytest.param(
            {"evidence": [[3, 3]]},
            "the fact 3 days / three days is not in its evidence lines",
            id="evidence_on_the_wrong_line",
        ),
    ],
)
def test_invalid_question_is_an_error_naming_it(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    question = REMOTE_DAYS | changes
    folder = write_set(tmp_path / "evals", as_toml(PARKING, question))

    error = load_error(folder)

    assert error.startswith(f"Question {question['id']}: ")
    assert message in error


def test_evidence_can_span_several_ranges(tmp_path: Path) -> None:
    question = REMOTE_DAYS | {
        "category": "multi_fact",
        "facts": [["3 days"], ["8:00"]],
        "evidence": [[2, 2], [3, 3]],
    }
    folder = write_set(tmp_path / "evals", as_toml(question))

    question_set = load_question_set(folder)

    assert question_set.questions[0].evidence == [
        LineRange("handbook.md", 2, 2),
        LineRange("handbook.md", 3, 3),
    ]


def test_evidence_may_name_the_questions_own_document(tmp_path: Path) -> None:
    question = REMOTE_DAYS | {"evidence": [["handbook.md", 2, 2]]}
    folder = write_set(tmp_path / "evals", as_toml(question))

    question_set = load_question_set(folder)

    assert question_set.questions == [Question.model_validate(REMOTE_DAYS)]


def test_cross_document_question_has_evidence_in_each_of_its_files(
    tmp_path: Path,
) -> None:
    folder = write_set(
        tmp_path / "evals", as_toml(REMOTE_DAYS_AND_DRESS), TWO_DOCUMENTS
    )

    [question] = load_question_set(folder).questions

    assert question.answerable
    assert question.evidence == [
        LineRange("handbook.md", 2, 2),
        LineRange("rules.md", 2, 2),
    ]
    assert question.files == ["handbook.md", "rules.md"]


def test_files_of_a_question_are_its_document_then_the_others_in_order() -> None:
    question = Question.model_validate(
        REMOTE_DAYS_AND_DRESS
        | {
            "evidence": [
                ["c.md", 1, 1],
                [2, 2],
                ["b.md", 1, 1],
                ["c.md", 3, 3],
            ]
        }
    )

    assert question.files == ["handbook.md", "c.md", "b.md"]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        pytest.param(
            {"evidence": [[2, 2], [3, 3]], "facts": [["3 days"]]},
            "a cross_document question needs evidence in its own document and in at "
            "least one other",
            id="evidence_in_its_own_document_only",
        ),
        pytest.param(
            {"evidence": [["rules.md", 2, 2]], "facts": [["dress well"]]},
            "a cross_document question needs evidence in its own document and in at "
            "least one other",
            id="evidence_in_another_document_only",
        ),
        pytest.param(
            {"evidence": [[2, 2], ["missing.md", 1, 1]]},
            "missing.md is not in",
            id="evidence_in_a_missing_file",
        ),
        pytest.param(
            {"evidence": [[2, 2], ["rules.md", 3, 2]]},
            "evidence [3, 2] in rules.md ends before it starts",
            id="evidence_backwards",
        ),
        pytest.param(
            {"evidence": [[2, 2], ["rules.md", 2, 4]]},
            "evidence [2, 4] is outside rules.md, which has 3 lines",
            id="evidence_past_the_end_of_the_other_file",
        ),
        pytest.param(
            {"evidence": [[2, 2], ["rules.md", 3, 3]]},
            "the fact dress well is not in its evidence lines",
            id="evidence_on_the_wrong_line_of_the_other_file",
        ),
    ],
)
def test_invalid_cross_document_question_is_an_error_naming_it(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    question = REMOTE_DAYS_AND_DRESS | changes
    folder = write_set(tmp_path / "evals", as_toml(question), TWO_DOCUMENTS)

    error = load_error(folder)

    assert error.startswith(f"Question {question['id']}: ")
    assert message in error


@pytest.mark.parametrize("category", ["fact", "multi_fact", "injection"])
def test_only_a_cross_document_question_has_evidence_in_another_file(
    tmp_path: Path, category: str
) -> None:
    question = REMOTE_DAYS_AND_DRESS | {"category": category}
    folder = write_set(tmp_path / "evals", as_toml(question), TWO_DOCUMENTS)

    error = load_error(folder)

    assert error == (
        f"Question handbook-remote-days-and-dress: a {category} question can only "
        "have evidence in its own document, handbook.md."
    )


def test_evidence_in_a_hidden_file_is_an_error(tmp_path: Path) -> None:
    question = REMOTE_DAYS_AND_DRESS | {"evidence": [[2, 2], [".rules.md", 2, 2]]}
    documents = {"handbook.md": HANDBOOK.encode(), ".rules.md": RULES.encode()}
    folder = write_set(tmp_path / "evals", as_toml(question), documents)

    error = load_error(folder)

    assert error == (
        "Question handbook-remote-days-and-dress: .rules.md is not in "
        f"{folder / 'documents'}."
    )


def test_clarify_question_has_its_reply_and_the_cases_it_cant_tell_apart(
    tmp_path: Path,
) -> None:
    question = OPENING_TIME | {"reply": "  I work in Brno.\n"}
    folder = write_set(tmp_path / "evals", as_toml(question), WITH_OFFICES)

    [loaded] = load_question_set(folder).questions

    assert loaded.reply == "I work in Brno."
    assert loaded.evidence == [LineRange("offices.md", 3, 3)]
    assert loaded.cases == [
        LineRange("offices.md", 2, 3),
        LineRange("handbook.md", 3, 3),
    ]
    assert loaded.files == ["offices.md", "handbook.md"]
    assert not loaded.answerable


def test_other_questions_have_no_reply_or_cases(tmp_path: Path) -> None:
    folder = write_set(tmp_path / "evals", as_toml(REMOTE_DAYS, PARKING))

    questions = load_question_set(folder).questions

    assert [(question.reply, question.cases) for question in questions] == [
        (None, []),
        (None, []),
    ]


def test_files_of_a_clarify_question_end_with_those_its_cases_are_in() -> None:
    question = Question.model_validate(
        OPENING_TIME
        | {
            "evidence": [["b.md", 1, 1], [3, 3]],
            "cases": [["c.md", 1, 1], ["b.md", 2, 2], [2, 2], ["a.md", 1, 1]],
        }
    )

    assert question.files == ["offices.md", "b.md", "c.md", "a.md"]


@pytest.mark.parametrize(
    ("question", "message"),
    [
        pytest.param(
            without(OPENING_TIME, "reply"),
            "a clarify question needs a reply",
            id="no_reply",
        ),
        pytest.param(
            OPENING_TIME | {"reply": " \n"}, "reply: String", id="blank_reply"
        ),
        pytest.param(
            OPENING_TIME | {"reply": "Brno" * 501},
            "reply: String should have at most 2000 characters",
            id="reply_longer_than_the_api_takes",
        ),
        pytest.param(
            without(OPENING_TIME, "cases"),
            "a clarify question needs cases",
            id="no_cases",
        ),
        pytest.param(
            OPENING_TIME | {"cases": []},
            "a clarify question needs cases",
            id="empty_cases",
        ),
        pytest.param(
            OPENING_TIME | {"cases": [[2, 2], [3]]},
            "cases: entry 2 must be [start, end] or [file, start, end]",
            id="case_not_a_pair",
        ),
        pytest.param(
            OPENING_TIME | {"cases": "2-3"}, "cases: Input", id="cases_not_a_list"
        ),
        pytest.param(
            OPENING_TIME | {"cases": [[3, 2]]},
            "case [3, 2] in offices.md ends before it starts",
            id="case_backwards",
        ),
        pytest.param(
            OPENING_TIME | {"cases": [[0, 2]]},
            "case [0, 2] is outside offices.md, which has 3 lines",
            id="case_from_line_zero",
        ),
        pytest.param(
            OPENING_TIME | {"cases": [[2, 4]]},
            "case [2, 4] is outside offices.md, which has 3 lines",
            id="case_past_the_end",
        ),
        pytest.param(
            OPENING_TIME | {"cases": [[2, 3], ["handbook.md", 3, 4]]},
            "case [3, 4] is outside handbook.md, which has 3 lines",
            id="case_past_the_end_of_another_file",
        ),
        pytest.param(
            OPENING_TIME | {"cases": [[2, 3], ["missing.md", 1, 1]]},
            "missing.md is not in",
            id="case_in_a_missing_file",
        ),
        pytest.param(
            OPENING_TIME | {"facts": []},
            "a clarify question needs facts",
            id="no_facts",
        ),
        pytest.param(
            OPENING_TIME | {"evidence": []},
            "a clarify question needs evidence",
            id="no_evidence",
        ),
        pytest.param(
            OPENING_TIME | {"evidence": [[3, 3], ["handbook.md", 3, 3]]},
            "a clarify question can only have evidence in its own document, offices.md",
            id="evidence_in_another_file_too",
        ),
        pytest.param(
            OPENING_TIME | {"evidence": [["handbook.md", 3, 3]], "facts": [["8:00"]]},
            "a clarify question can only have evidence in its own document, offices.md",
            id="evidence_only_in_another_file",
        ),
        pytest.param(
            OPENING_TIME | {"evidence": [[2, 2]]},
            "the fact 9:00 / nine is not in its evidence lines",
            id="fact_only_in_a_case",
        ),
    ],
)
def test_invalid_clarify_question_is_an_error_naming_it(
    tmp_path: Path, question: dict[str, object], message: str
) -> None:
    folder = write_set(tmp_path / "evals", as_toml(question), WITH_OFFICES)

    error = load_error(folder)

    assert error.startswith("Question offices-opening-time: ")
    assert message in error


@pytest.mark.parametrize(
    "question",
    [
        pytest.param(REMOTE_DAYS | {"reply": "Brno."}, id="fact_with_a_reply"),
        pytest.param(REMOTE_DAYS | {"cases": [[2, 2]]}, id="fact_with_cases"),
        pytest.param(
            REMOTE_DAYS_AND_DRESS | {"reply": "Brno."}, id="cross_document_with_a_reply"
        ),
        pytest.param(PARKING | {"reply": "Brno."}, id="unanswerable_with_a_reply"),
        pytest.param(PARKING | {"cases": [[2, 2]]}, id="unanswerable_with_cases"),
    ],
)
def test_only_a_clarify_question_has_a_reply_or_cases(
    tmp_path: Path, question: dict[str, object]
) -> None:
    folder = write_set(tmp_path / "evals", as_toml(question), TWO_DOCUMENTS)

    error = load_error(folder)

    assert error == (
        f"Question {question['id']}: a {question['category']} question can't have "
        "a reply or cases."
    )


def test_question_without_an_id_is_named_by_its_position(
    tmp_path: Path,
) -> None:
    question = without(REMOTE_DAYS, "id")
    folder = write_set(tmp_path / "evals", as_toml(PARKING, question))

    error = load_error(folder)

    assert error.startswith("Question number 2: id: Field required")


def test_duplicate_ids_are_an_error(tmp_path: Path) -> None:
    folder = write_set(
        tmp_path / "evals", as_toml(REMOTE_DAYS, PARKING | {"id": REMOTE_DAYS["id"]})
    )

    error = load_error(folder)

    assert error == ("Question handbook-remote-days: another question has the same id.")


@pytest.mark.parametrize(
    ("questions_toml", "message"),
    [
        pytest.param(b"[[questions]\nid = ", "is not valid TOML", id="broken_toml"),
        pytest.param(b'title = "caf\xe9"\n', "is not valid TOML", id="not_utf8"),
        pytest.param(b"", "questions: Field required", id="empty_file"),
        pytest.param(b"questions = []\n", "questions: List should", id="no_questions"),
        pytest.param(
            b'title = "Baseline"\n' + as_toml(REMOTE_DAYS).encode(),
            "title: Extra inputs",
            id="unknown_top_level_key",
        ),
        pytest.param(
            b'questions = ["handbook-remote-days"]\n',
            "questions.0: Input should be a valid dictionary",
            id="question_not_a_table",
        ),
    ],
)
def test_unreadable_questions_file_is_an_error_naming_it(
    tmp_path: Path, questions_toml: bytes, message: str
) -> None:
    folder = write_set(tmp_path / "evals", questions_toml)

    error = load_error(folder)

    assert error.startswith(str(folder / "questions.toml"))
    assert message in error


def test_missing_questions_file_is_an_error(tmp_path: Path) -> None:
    error = load_error(tmp_path / "evals")

    assert error.startswith(f"Can't read {tmp_path / 'evals' / 'questions.toml'}")


def test_missing_documents_folder_is_an_error(tmp_path: Path) -> None:
    folder = tmp_path / "evals"
    folder.mkdir()
    (folder / "questions.toml").write_text(as_toml(REMOTE_DAYS))

    error = load_error(folder)

    assert error.startswith(f"Can't read {folder / 'documents'}")


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        pytest.param("handbook.pdf", HANDBOOK.encode(), "Only .txt and .md", id="pdf"),
        pytest.param("handbook", HANDBOOK.encode(), "Only .txt and .md", id="no_ext"),
        pytest.param("handbook.md", b"caf\xe9", "UTF-8", id="invalid_utf8"),
        pytest.param("handbook.md", b"a\x00b", "NUL", id="nul_character"),
        pytest.param("handbook.md", b"", "empty", id="empty_file"),
        pytest.param("handbook.md", b" \r\n\t", "empty", id="whitespace_only"),
        pytest.param(
            "handbook.md", b"x" * 1_000_001, "larger than 1,000,000", id="too_large"
        ),
    ],
)
def test_documents_follow_the_upload_rules(
    tmp_path: Path, filename: str, content: bytes, message: str
) -> None:
    question = PARKING | {"document": filename}
    folder = write_set(tmp_path / "evals", as_toml(question), {filename: content})

    error = load_error(folder)

    assert error.startswith(f"{folder / 'documents' / filename}: ")
    assert message in error


def test_documents_no_question_is_about_follow_the_upload_rules_too(
    tmp_path: Path,
) -> None:
    documents = {"handbook.md": HANDBOOK.encode(), "notes.pdf": b"%PDF-1.7"}
    folder = write_set(tmp_path / "evals", as_toml(REMOTE_DAYS), documents)

    error = load_error(folder)

    assert error == (
        f"{folder / 'documents' / 'notes.pdf'}: Only .txt and .md files are accepted."
    )


@pytest.mark.parametrize(
    "line_ending",
    [
        pytest.param("\r\n", id="crlf"),
        pytest.param("\r", id="cr"),
    ],
)
def test_line_endings_are_normalized_so_line_numbers_match(
    tmp_path: Path, line_ending: str
) -> None:
    document = HANDBOOK.replace("\n", line_ending).encode()
    folder = write_set(
        tmp_path / "evals", as_toml(REMOTE_DAYS), {"handbook.md": document}
    )

    question_set = load_question_set(folder)

    assert question_set.documents["handbook.md"].lines == HANDBOOK.splitlines()


def test_byte_order_mark_is_dropped(tmp_path: Path) -> None:
    document = b"\xef\xbb\xbf" + HANDBOOK.encode()
    folder = write_set(
        tmp_path / "evals", as_toml(REMOTE_DAYS), {"handbook.md": document}
    )

    question_set = load_question_set(folder)

    assert question_set.documents["handbook.md"].text == HANDBOOK


def two_document_set(tmp_path: Path) -> QuestionSet:
    rules = PARKING | {"id": "rules-dress-code", "document": "rules.md"}
    documents = {"handbook.md": HANDBOOK.encode(), "rules.md": b"Dress well.\n"}
    folder = write_set(
        tmp_path / "evals", as_toml(rules, REMOTE_DAYS, PARKING), documents
    )
    return load_question_set(folder)


def test_selected_questions_keep_their_order_and_every_document(
    tmp_path: Path,
) -> None:
    question_set = two_document_set(tmp_path)

    selected = select_questions(
        question_set, ["handbook-parking", "handbook-remote-days"]
    )

    assert [question.id for question in selected.questions] == [
        "handbook-remote-days",
        "handbook-parking",
    ]
    assert list(selected.documents) == ["handbook.md", "rules.md"]
    assert selected.documents == question_set.documents
    assert selected.fingerprint == question_set.fingerprint


def test_selecting_an_unknown_id_is_an_error(tmp_path: Path) -> None:
    question_set = two_document_set(tmp_path)

    with pytest.raises(InvalidQuestionSetError) as error:
        select_questions(question_set, ["handbook-parking", "nope", "also-nope"])

    assert str(error.value) == "No question has the id also-nope, nope."
