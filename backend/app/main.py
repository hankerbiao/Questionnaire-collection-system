import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from app.api import router
from app.admin_api import router as admin_router
from app.config import get_settings
from app.default_survey import default_survey
from app.repository import SubmissionRepository
from app.user_api import router as user_router
from app.user_submissions_api import router as user_submissions_router

logger = logging.getLogger(__name__)


def configure_application_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    application_logger = logging.getLogger("app")
    application_logger.setLevel(level)

    uvicorn_handlers = (
        logging.getLogger("uvicorn").handlers
        or logging.getLogger("uvicorn.error").handlers
    )
    if uvicorn_handlers:
        application_logger.handlers = list(uvicorn_handlers)
        application_logger.propagate = False


async def reconcile_orphans(repository: SubmissionRepository) -> None:
    try:
        deleted_orphans = await repository.reconcile_orphan_attachments()
        if deleted_orphans:
            logger.warning("Removed %s orphaned GridFS attachments", deleted_orphans)
    except Exception:
        logger.exception("GridFS orphan reconciliation failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_application_logging(settings.log_level)
    logger.info("Application log level: %s", logging.getLevelName(logger.getEffectiveLevel()))
    client = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
    )
    repository = SubmissionRepository(client, settings.mongodb_database)
    app.state.repository = repository
    reconciliation_task: asyncio.Task[None] | None = None
    try:
        await repository.ping()
        await repository.ensure_indexes()
        await repository.ensure_default_survey(
            default_survey("published", 1),
            default_survey("draft", 0),
        )
        reconciliation_task = asyncio.create_task(reconcile_orphans(repository))
    except PyMongoError:
        logger.warning("MongoDB is not ready during startup; readiness will remain unhealthy")
    try:
        yield
    finally:
        if reconciliation_task is not None:
            if not reconciliation_task.done():
                reconciliation_task.cancel()
            with suppress(asyncio.CancelledError):
                await reconciliation_task
        await client.close()


app = FastAPI(
    title="DML v4 Survey API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(user_submissions_router)
app.include_router(user_router)
app.include_router(admin_router)
