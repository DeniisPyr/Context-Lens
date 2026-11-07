# Here rather than in the client, so that the database can know it without importing
# the client. Gemini is asked for exactly this many numbers in every embedding, and the
# chunks table holds exactly this many, so changing it needs a migration.
EMBEDDING_DIMENSIONS = 768


def document_embedding_text(title: str, text: str) -> str:
    # gemini-embedding-2 takes no task type, so the text says what it is: the format
    # Google gives for documents that a search should find.
    return f"title: {title} | text: {text}"
