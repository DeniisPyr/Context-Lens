from dataclasses import dataclass

MAX_CHUNK_CHARACTERS = 1000
# A block of text this short, between blank lines, is taken for a heading.
MAX_HEADING_LINES = 2
MAX_HEADING_CHARACTERS = 80


@dataclass(frozen=True)
class TextChunk:
    # Numbered from 1 and inclusive, like the lines of a citation.
    start_line: int
    end_line: int
    text: str


def _is_blank(line: str) -> bool:
    return not line.strip()


def _joined_length(lines: list[str]) -> int:
    return sum(map(len, lines)) + max(len(lines) - 1, 0)


def _chunk(lines: list[str], start: int, end: int) -> list[TextChunk]:
    # Blank lines at the ends would only widen the line range a search result shows.
    while start < end and _is_blank(lines[start]):
        start += 1
    while end > start and _is_blank(lines[end - 1]):
        end -= 1
    if start == end:
        return []
    return [TextChunk(start + 1, end, "\n".join(lines[start:end]))]


def _last_blank_line(lines: list[str], start: int, end: int) -> int | None:
    # Only past the first third, so that ending the chunk there doesn't leave a small
    # one behind.
    length = _joined_length(lines[start:end])
    found = None
    offset = 0
    for index in range(start, end):
        if offset >= length / 3 and _is_blank(lines[index]):
            found = index
        offset += len(lines[index]) + 1
    return found


def _heading_before(lines: list[str], start: int, end: int) -> int | None:
    # Where the block of text ending at lines[end - 1] begins, if the block is short
    # enough to be a heading, such as "## 5. Sick leave" or a title underlined with ===.
    begin = end
    while begin > start and not _is_blank(lines[begin - 1]):
        begin -= 1
    block = lines[begin:end]
    if not block or len(block) > MAX_HEADING_LINES:
        return None
    if any(len(line.strip()) > MAX_HEADING_CHARACTERS for line in block):
        return None
    return begin


def _cut(lines: list[str], start: int, end: int) -> tuple[int, int]:
    # Where the full chunk lines[start:end] ends, and where the next one starts.
    # Ending at a blank line keeps the paragraph, list entry or error code after it
    # together in the next chunk.
    blank = _last_blank_line(lines, start, end)
    if blank is None:
        return end, end
    # Headings just before that blank line introduce the text after it, so they go
    # with it into the next chunk, however many are stacked up.
    moved = None
    cut = blank
    while (begin := _heading_before(lines, start, cut)) is not None:
        moved = cut = begin
        while cut > start and _is_blank(lines[cut - 1]):
            cut -= 1
    if moved is None:
        return blank, blank + 1
    if all(_is_blank(line) for line in lines[start:moved]):
        # Headings are all this chunk has, so it stays whole.
        return end, end
    return moved, moved


def _split_long_line(line: str, number: int) -> list[TextChunk]:
    chunks = []
    rest = line.strip()
    while len(rest) > MAX_CHUNK_CHARACTERS:
        # At the last whitespace that leaves the piece before it short enough, or in
        # the middle of a word when there is none.
        cut = next(
            (
                index
                for index in range(MAX_CHUNK_CHARACTERS, 0, -1)
                if rest[index].isspace()
            ),
            MAX_CHUNK_CHARACTERS,
        )
        chunks.append(TextChunk(number, number, rest[:cut].rstrip()))
        rest = rest[cut:].lstrip()
    if rest:
        chunks.append(TextChunk(number, number, rest))
    return chunks


def split_into_chunks(lines: list[str]) -> list[TextChunk]:
    chunks = []
    # The chunk being filled is lines[start:end], and length is its joined length.
    start = end = length = 0
    while end < len(lines):
        line = lines[end]
        if start == end and len(line) > MAX_CHUNK_CHARACTERS:
            chunks += _split_long_line(line, end + 1)
            start = end = end + 1
            continue
        grown = len(line) if start == end else length + 1 + len(line)
        if grown <= MAX_CHUNK_CHARACTERS:
            length = grown
            end += 1
            continue
        # The next line doesn't fit, so this chunk ends.
        cut, next_start = _cut(lines, start, end)
        chunks += _chunk(lines, start, cut)
        start = next_start
        length = _joined_length(lines[start:end])
    chunks += _chunk(lines, start, end)
    return chunks
