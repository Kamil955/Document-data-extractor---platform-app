import uuid
from collections.abc import AsyncIterator

import pytest

from app.core.config import get_settings
from app.storage.azure_blob import AzureBlobStorage
from app.storage.base import BlobNotFoundError

pytestmark = pytest.mark.integration  # needs a running floci-az (or Azurite) emulator


@pytest.fixture
async def blob_storage() -> AsyncIterator[AzureBlobStorage]:
    # A fresh container per test keeps tests independent of each other and of earlier runs.
    container = f"test-{uuid.uuid4().hex[:12]}"
    storage = AzureBlobStorage(get_settings().azure_storage_connection_string, container)
    await storage.start()
    try:
        yield storage
    finally:
        await storage._container.delete_container()
        await storage.close()


async def test_put_get_roundtrip(blob_storage: AzureBlobStorage) -> None:
    await blob_storage.put("documents/a", b"hello", "application/pdf")
    assert await blob_storage.get("documents/a") == b"hello"


async def test_get_missing_blob_raises(blob_storage: AzureBlobStorage) -> None:
    with pytest.raises(BlobNotFoundError):
        await blob_storage.get("documents/missing")


async def test_delete_is_idempotent(blob_storage: AzureBlobStorage) -> None:
    await blob_storage.put("documents/a", b"hello", "application/pdf")
    await blob_storage.delete("documents/a")
    await blob_storage.delete("documents/a")  # second delete must not raise
    with pytest.raises(BlobNotFoundError):
        await blob_storage.get("documents/a")


async def test_start_is_safe_to_call_twice(blob_storage: AzureBlobStorage) -> None:
    await blob_storage.start()  # container already exists
