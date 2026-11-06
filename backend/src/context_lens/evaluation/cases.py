import hashlib
import re
import tomllib
from collections.abc import Collection
from dataclasses import dataclass, replace
from itertools import chain
from pathlib import Path
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from context_lens.evaluation.matching import contains_phrase
from context_lens.services.documents import Document, InvalidDocumentError, add_upload
from context_lens.settings import Settings

Category = Literal[
    "fact", "multi_fact", "injection", "missing_related", "missing_unrelated"
]
CATEGORIES: tuple[Category, ...] = get_args(Category)
ANSWERABLE: frozenset[Category] = frozenset({"fact", "multi_fact", "injection"})

ID_PATTERN = re.compile(r"[a-z0-9-]+")
# Settings() would need a Gemini key, and only the default limit is wanted here.
MAX_UPLOAD_BYTES: int = Settings.model_fields["max_upload_bytes"].default


class InvalidQuestionSetError(Exception):
    """The question set can't be used; the message names the question or file."""


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
    evidence: list[tuple[int, int]] = []
    forbidden: list[str] = []

    @property
    def answerable(self) -> bool:
        return self.category in ANSWERABLE


class _QuestionsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Checked one by one later, so that an error can name the question.
    questions: list[dict[str, object]] = Field(min_length=1)


@dataclass(frozen=True)
class QuestionSet:
    questions: list[Question]
    documents: dict[str, Document]
    fingerprint: str


class _KeepNothing:
    # add_upload checks a file and hands it to a store; this one just hands it back.
    async def add(self, dataset_id: str, filename: str, text: str) -> Document:
        return Document(id=filename, filename=filename, text=text)

    async def get(self, document_id: str) -> Document | None:
        return None


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
    return {path.name: path for path in paths if path.is_file()}


def _parse_entry(entry: dict[str, object], number: int) -> Question:
    try:
        return Question.model_validate(entry)
    except ValidationError as exc:
        name = entry.get("id", f"number {number}")
        raise InvalidQuestionSetError(f"Question {name}: {_describe(exc)}.") from None


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


async def _as_document(path: Path, data: bytes) -> Document:
    # Through the upload code, so eval documents follow the rules and line numbers of
    # a real upload.
    try:
        return await add_upload(
            _KeepNothing(), "evaluation", path.name, data, MAX_UPLOAD_BYTES
        )
    except InvalidDocumentError as exc:
        raise InvalidQuestionSetError(f"{path}: {exc}") from None


def _check_evidence(question: Question, document: Document) -> None:
    lines = document.lines
    for start, end in question.evidence:
        if start > end:
            raise _problem(question, f"evidence [{start}, {end}] ends before it starts")
        if start < 1 or end > len(lines):
            raise _problem(
                question,
                f"evidence [{start}, {end}] is outside {document.filename}, "
                f"which has {len(lines)} lines",
            )
    # Catches line numbers that point at the wrong place.
    text = "\n".join(
        line for start, end in question.evidence for line in lines[start - 1 : end]
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


async def load_question_set(folder: Path) -> QuestionSet:
    questions_path = folder / "questions.toml"
    questions_file = _read(questions_path)
    questions = _parse_questions(questions_file, questions_path)

    documents_folder = folder / "documents"
    available = _list_files(documents_folder)
    for question in questions:
        if question.document not in available:
            raise _problem(
                question, f"{question.document} is not in {documents_folder}"
            )
    # Only the documents that questions use, so stray files such as .DS_Store don't
    # break the set or change its fingerprint.
    names = sorted({question.document for question in questions})
    files = {name: _read(available[name]) for name in names}
    documents = {
        name: await _as_document(available[name], data) for name, data in files.items()
    }

    for question in questions:
        _check_evidence(question, documents[question.document])
    return QuestionSet(questions, documents, _fingerprint(questions_file, files))


def select_questions(question_set: QuestionSet, ids: Collection[str]) -> QuestionSet:
    known = {question.id for question in question_set.questions}
    unknown = sorted(set(ids) - known)
    if unknown:
        raise InvalidQuestionSetError(f"No question has the id {', '.join(unknown)}.")
    questions = [question for question in question_set.questions if question.id in ids]
    names = sorted({question.document for question in questions})
    documents = {name: question_set.documents[name] for name in names}
    return replace(question_set, questions=questions, documents=documents)
