from uuid import UUID


def parse_id(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        # Ids come straight from the API, and this one can't belong to anything.
        return None
