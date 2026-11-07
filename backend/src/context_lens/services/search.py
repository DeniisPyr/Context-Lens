from dataclasses import dataclass


@dataclass(frozen=True)
class FoundChunk:
    document_id: str
    filename: str
    # Where the chunk comes in its document, counted from 0.
    position: int
    # Numbered from 1 and inclusive, like the lines of a citation.
    start_line: int
    end_line: int
    text: str
