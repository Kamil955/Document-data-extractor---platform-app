from typing import Protocol


class BlobNotFoundError(Exception):
    """Raised when a blob does not exist in storage."""


class BlobStorage(Protocol):
    """What the application needs from file storage, and nothing more.

    The API code depends on this interface, not on Azure. Tests plug in an in-memory
    implementation, and a different backend (S3, local disk) would not touch the API.
    """

    # overwrite=False refuses to replace an existing blob (keys of documents are unique UUIDs,
    # so a clash is a bug); overwrite=True is for files that are replaced on purpose.
    async def put(
        self, key: str, data: bytes, content_type: str, overwrite: bool = False
    ) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...
