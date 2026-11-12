from app.storage.base import BlobNotFoundError


class InMemoryStorage:
    """A BlobStorage that keeps files in a dict. Fast, and needs no emulator."""

    def __init__(self) -> None:
        self.blobs: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.blobs[key] = (data, content_type)

    async def get(self, key: str) -> bytes:
        try:
            return self.blobs[key][0]
        except KeyError:
            raise BlobNotFoundError(key) from None

    async def delete(self, key: str) -> None:
        self.blobs.pop(key, None)
