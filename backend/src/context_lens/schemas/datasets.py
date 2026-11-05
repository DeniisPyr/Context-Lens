from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from context_lens.services.datasets import Dataset


class DatasetCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def has_no_nul(cls, name: str) -> str:
        # Postgres can't store this character, and would answer with an error.
        if "\x00" in name:
            raise ValueError("The name must not contain NUL characters.")
        return name


class DatasetResponse(BaseModel):
    id: str
    name: str

    @classmethod
    def from_dataset(cls, dataset: Dataset) -> Self:
        return cls(id=dataset.id, name=dataset.name)
