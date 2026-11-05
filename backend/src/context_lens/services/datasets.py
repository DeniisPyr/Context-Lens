from dataclasses import dataclass


class DatasetNameTakenError(Exception):
    """Another dataset already has this name."""

    def __init__(self) -> None:
        super().__init__("A dataset with this name already exists.")


class DatasetNotFoundError(Exception):
    """No dataset has the requested id."""

    def __init__(self) -> None:
        super().__init__("Dataset not found.")


@dataclass(frozen=True)
class Dataset:
    id: str
    name: str
