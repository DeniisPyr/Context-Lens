from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from context_lens.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), follow_redirects=False) as test_client:
        yield test_client
