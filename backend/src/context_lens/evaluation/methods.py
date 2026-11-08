from dataclasses import dataclass

from context_lens.clients.gemini import GeminiClient
from context_lens.evaluation.cases import Question
from context_lens.services.answering import (
    SYSTEM_INSTRUCTION,
    Excerpt,
    ModelAnswer,
    ask_about_excerpts,
    build_prompt,
    verify_answer,
)
from context_lens.services.documents import Document


def document_excerpt(document: Document) -> Excerpt:
    # The whole document, so the lines Gemini is shown are the real ones.
    lines = dict(enumerate(document.lines, start=1))
    return Excerpt(document_id=document.id, filename=document.filename, lines=lines)


@dataclass(frozen=True)
class WholeDocuments:
    """How the app answered before search: with the documents whole in the prompt."""

    documents: dict[str, Document]

    def excerpts(self, question: Question) -> list[Excerpt]:
        # The question's own document first, then the others its evidence is in.
        return [document_excerpt(self.documents[name]) for name in question.files]

    def prompt_characters(self, question: Question) -> int:
        prompt = build_prompt(question.question, self.excerpts(question))
        return len(SYSTEM_INSTRUCTION) + len(prompt)

    async def answer(self, question: Question, gemini: GeminiClient) -> ModelAnswer:
        excerpts = self.excerpts(question)
        answer = await ask_about_excerpts(question.question, excerpts, gemini)
        return verify_answer(answer, excerpts)
