import hashlib
import re
import tomllib
from collections.abc import Collection
from dataclasses import dataclass, replace
from itertools import chain
from pathlib import Path
from typing import Annotated, Literal, NamedTuple, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from context_lens.evaluation.matching import contains_phrase
from context_lens.services.documents import Document, InvalidDocumentError, read_upload
from context_lens.settings import Settings

Category = Literal[
    "fact",
    "multi_fact",
    "cross_document",
    "injection",
    "missing_related",
    "missing_unrelated",
]
CATEGORIES: tuple[Category, ...] = get_args(Category)
ANSWERABLE: frozenset[Category] = frozenset(
    {"fact", "multi_fact", "cross_document", "injection"}
)

ID_PATTERN = re.compile(r"[a-z0-9-]+")
# Settings() would need a Gemini key, and only the default limit is wanted here.
MAX_UPLOAD_BYTES: int = Settings.model_fields["max_upload_bytes"].default


class InvalidQuestionSetError(Exception):
    """The question set can't be used; the message names the question or file."""


class LineRange(NamedTuple):
    # Lines of one file in documents/, numbered from 1 and inclusive.
    file: str
    start: int
    end: int


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    document: str
    category: Category
    # The API's limits, so that every question could be asked there too.
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    facts: list[list[str]] = []
    # Written as [start, end] for lines of the question's document, or as
    # [file, start, end] for lines of any file, and kept in the second form.
    evidence: list[LineRange] = []
    forbidden: list[str] = []

    @field_validator("evidence", mode="before")
    @classmethod
    def _name_each_file(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, list):
            # Pydantic's own error says that it must be a list.
            return value
        # A question whose document is missing fails on that, so any name does here.
        document = info.data.get("document", "")
        ranges = []
        for number, entry in enumerate(value, start=1):
            match entry:
                case [int(), int()]:
                    ranges.append([document, *entry])
                case [str(), int(), int()]:
                    ranges.append(entry)
                case _:
                    raise PydanticCustomError(
                        "evidence_entry",
                        "entry {number} must be [start, end] or [file, start, end]",
                        {"number": number},
                    )
        return ranges

    @property
    def answerable(self) -> bool:
        return self.category in ANSWERABLE

    @property
    def files(self) -> list[str]:
        # Its document first, then each other file its evidence is in, in order.
        named = [self.document, *(lines.file for lines in self.evidence)]
        return list(dict.fromkeys(named))


class _QuestionsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Checked one by one later, so that an error can name the question.
    questions: list[dict[str, object]] = Field(min_length=1)


@dataclass(frozen=True)
class QuestionSet:
    questions: list[Question]
    documents: dict[str, Document]
    fingerprint: str


def _problem(question: Question, problem: str) -> InvalidQuestionSetError:
    return InvalidQuestionSetError(f"Question {question.id}: {problem}.")


def _describe(error: ValidationError) -> str:
    # Not str(error): it repeats the input, which makes long messages for one typo.
    return "; ".join(
        f"{'.'.join(map(str, detail['loc']))}: {detail['msg']}"
        for detail in error.errors()
    )


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise InvalidQuestionSetError(f"Can't read {path}: {exc.strerror}.") from None


def _list_files(folder: Path) -> dict[str, Path]:
    try:
        paths = sorted(folder.iterdir())
    except OSError as exc:
        raise InvalidQuestionSetError(f"Can't read {folder}: {exc.strerror}.") from None
    # Hidden files, such as .DS_Store, aren't documents.
    return {
        path.name: path
        for path in paths
        if path.is_file() and not path.name.startswith(".")
    }


def _parse_entry(entry: dict[str, object], number: int) -> Question:
    try:
        return Question.model_validate(entry)
    except ValidationError as exc:
        name = entry.get("id", f"number {number}")
        raise InvalidQuestionSetError(f"Question {name}: {_describe(exc)}.") from None


def _check_evidence_files(question: Question) -> None:
    in_document = any(lines.file == question.document for lines in question.evidence)
    elsewhere = len(question.files) > 1
    if question.category == "cross_document":
        if not (in_document and elsewhere):
            raise _problem(
                question,
                "a cross_document question needs evidence in its own document and "
                "in at least one other",
            )
    elif elsewhere:
        raise _problem(
            question,
            f"a {question.category} question can only have evidence in its own "
            f"document, {question.document}",
        )


def _check_question(question: Question) -> None:
    if not ID_PATTERN.fullmatch(question.id):
        raise _problem(question, "the id must be lowercase letters, digits and hyphens")
    if question.answerable:
        if not question.facts:
            raise _problem(question, f"a {question.category} question needs facts")
        if not all(question.facts):
            raise _problem(question, "every fact needs at least one phrasing")
        if not question.evidence:
            raise _problem(question, f"a {question.category} question needs evidence")
        _check_evidence_files(question)
    elif question.facts or question.evidence:
        raise _problem(
            question, f"a {question.category} question can't have facts or evidence"
        )
    # An empty phrase would be found in every answer.
    if not all(phrase.strip() for phrase in chain(*question.facts, question.forbidden)):
        raise _problem(question, "facts and forbidden phrases must not be empty")


def _parse_questions(data: bytes, path: Path) -> list[Question]:
    try:
        content = tomllib.loads(data.decode())
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise InvalidQuestionSetError(f"{path} is not valid TOML: {exc}.") from None
    try:
        entries = _QuestionsFile.model_validate(content).questions
    except ValidationError as exc:
        raise InvalidQuestionSetError(f"{path}: {_describe(exc)}.") from None

    questions = []
    seen = set()
    for number, entry in enumerate(entries, start=1):
        question = _parse_entry(entry, number)
        _check_question(question)
        if question.id in seen:
            raise _problem(question, "another question has the same id")
        seen.add(question.id)
        questions.append(question)
    return questions


def _as_document(path: Path, data: bytes) -> Document:
    # Through the upload code, so eval documents follow the rules and line numbers of
    # a real upload.
    try:
        filename, text = read_upload(path.name, data, MAX_UPLOAD_BYTES)
    except InvalidDocumentError as exc:
        raise InvalidQuestionSetError(f"{path}: {exc}") from None
    return Document(id=filename, filename=filename, text=text)


def _check_evidence(question: Question, documents: dict[str, Document]) -> None:
    lines = {name: documents[name].lines for name in question.files}
    for file, start, end in question.evidence:
        if start > end:
            raise _problem(
                question, f"evidence [{start}, {end}] in {file} ends before it starts"
            )
        if start < 1 or end > len(lines[file]):
            raise _problem(
                question,
                f"evidence [{start}, {end}] is outside {file}, "
                f"which has {len(lines[file])} lines",
            )
    # Catches line numbers that point at the wrong place.
    text = "\n".join(
        line
        for file, start, end in question.evidence
        for line in lines[file][start - 1 : end]
    )
    for fact in question.facts:
        if not any(contains_phrase(text, phrase) for phrase in fact):
            raise _problem(
                question, f"the fact {' / '.join(fact)} is not in its evidence lines"
            )


def _fingerprint(questions_file: bytes, document_files: dict[str, bytes]) -> str:
    parts = [questions_file]
    for name in sorted(document_files):
        parts += [name.encode(), document_files[name]]
    digest = hashlib.sha256()
    for part in parts:
        # Each part's length first, so bytes moved from one part to the next still
        # change the digest.
        digest.update(len(part).to_bytes(8, "big") + part)
    return f"sha256:{digest.hexdigest()}"


def load_question_set(folder: Path) -> QuestionSet:
    questions_path = folder / "questions.toml"
    questions_file = _read(questions_path)
    questions = _parse_questions(questions_file, questions_path)

    documents_folder = folder / "documents"
    available = _list_files(documents_folder)
    for question in questions:
        for name in question.files:
            if name not in available:
                raise _problem(question, f"{name} is not in {documents_folder}")
    # Every document, whether a question is about it or not: the app searches a whole
    # dataset, so the others are there to be found instead.
    files = {name: _read(path) for name, path in available.items()}
    documents = {
        name: _as_document(available[name], data) for name, data in files.items()
    }

    for question in questions:
        _check_evidence(question, documents)
    return QuestionSet(questions, documents, _fingerprint(questions_file, files))


def select_questions(question_set: QuestionSet, ids: Collection[str]) -> QuestionSet:
    known = {question.id for question in question_set.questions}
    unknown = sorted(set(ids) - known)
    if unknown:
        raise InvalidQuestionSetError(f"No question has the id {', '.join(unknown)}.")
    questions = [question for question in question_set.questions if question.id in ids]
    # All the documents stay: fewer questions are asked of the same dataset.
    return replace(question_set, questions=questions)
