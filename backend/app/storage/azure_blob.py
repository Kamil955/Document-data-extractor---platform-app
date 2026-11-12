import asyncio
import logging

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError, ServiceRequestError
from azure.storage.blob import ContentSettings
from azure.storage.blob.aio import BlobServiceClient

from app.storage.base import BlobNotFoundError

logger = logging.getLogger(__name__)


class AzureBlobStorage:
    """BlobStorage backed by Azure Blob Storage (or the floci-az emulator)."""

    def __init__(self, connection_string: str, container: str) -> None:
        # The async client keeps the event loop free while bytes move over the network.
        self._service = BlobServiceClient.from_connection_string(connection_string)
        self._container = self._service.get_container_client(container)

    async def start(self, attempts: int = 15, delay_seconds: float = 1.0) -> None:
        """Create the container if it is missing. Retries while the server is starting.

        In docker compose the emulator may accept connections a moment after its
        container is "started", so a refused connection is retried instead of
        crashing the application on the first try.
        """
        for attempt in range(1, attempts + 1):
            try:
                # retry_total=0: one attempt per call. The SDK's own retry policy backs
                # off for over a minute on a refused connection, which would make
                # startup hang. Our loop below controls the waiting instead.
                await self._container.create_container(retry_total=0)
            except ResourceExistsError:
                return  # already there: fine, this is the normal case after the first run
            except ServiceRequestError:
                # Raised when the server cannot be reached at all (connection refused).
                if attempt == attempts:
                    raise
                logger.warning("Blob storage not reachable yet (attempt %s/%s)", attempt, attempts)
                await asyncio.sleep(delay_seconds)
            else:
                return

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        # overwrite=False: keys are unique UUIDs, so an existing blob means a bug.
        # We want a loud error there, not a silent overwrite of someone's file.
        await self._container.upload_blob(
            name=key,
            data=data,
            overwrite=False,
            content_settings=ContentSettings(content_type=content_type),
        )

    async def get(self, key: str) -> bytes:
        try:
            downloader = await self._container.download_blob(key)
            return await downloader.readall()
        except ResourceNotFoundError as exc:
            raise BlobNotFoundError(key) from exc

    async def delete(self, key: str) -> None:
        try:
            await self._container.delete_blob(key)
        except ResourceNotFoundError:
            # Deleting something that is already gone is a success, so cleanup code
            # can call this safely more than once.
            return

    async def close(self) -> None:
        await self._service.close()
