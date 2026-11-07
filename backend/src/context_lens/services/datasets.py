from dataclasses import dataclass


class DatasetNameTakenError(Exception):
    """Another dataset already has this name."""

    def __init__(self) -> None:
        super().__init__("A dataset with this name already exists.")


class DatasetNotFoundError(Exception):
    """No dataset has the requested id."""

    def __init__(self) -> None:
        super().__init__("Dataset not found.")


class DatasetFullError(Exception):
    """The dataset already holds as many documents as a dataset may."""

    def __init__(self, max_documents: int) -> None:
        super().__init__(
            f"This dataset already has {max_documents} documents, the most it can hold."
        )


@dataclass(frozen=True)
class Dataset:
    id: str
    name: str
