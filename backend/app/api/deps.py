from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.storage.base import BlobStorage


def get_storage(request: Request) -> BlobStorage:
    # The storage client is created once at startup (see lifespan in main.py)
    # and shared by all requests.
    return request.app.state.storage


# Annotated aliases keep endpoint signatures short and give tests one place to override.
SessionDep = Annotated[AsyncSession, Depends(get_session)]
StorageDep = Annotated[BlobStorage, Depends(get_storage)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
