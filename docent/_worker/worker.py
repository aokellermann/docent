import asyncio
import json
from typing import Any

import anyio
import redis.asyncio as redis
from arq import ArqRedis
from arq.connections import RedisSettings
from arq.worker import run_worker
from pydantic_core import to_jsonable_python

from docent._ai_tools.search import SearchResult
from docent._db_service.contexts import ViewContext
from docent._db_service.schemas.tables import JobStatus
from docent._db_service.service import DBService
from docent._env_util import ENV
from docent._log_util import get_logger
from docent._server._broker.redis_client import publish_framegrid_update
from docent._server._rest.send_state import publish_searches

logger = get_logger(__name__)


# Initialize Redis connection
REDIS_HOST = ENV.get("DOCENT_REDIS_HOST")
REDIS_PORT = ENV.get("DOCENT_REDIS_PORT")
if REDIS_HOST is None or REDIS_PORT is None:
    raise ValueError("DOCENT_REDIS_HOST and DOCENT_REDIS_PORT must be set")
REDIS = ArqRedis(
    connection_pool=redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
)


async def compute_search(_: dict[Any, Any], view_ctx: ViewContext, job_id: str, read_only: bool):
    db = await DBService.init()
    result = await db.get_search_job_and_query(job_id)
    if result is None:
        logger.error(f"Search job {job_id} not found")
        return
    _job, query = result

    await db.set_job_status(job_id, JobStatus.RUNNING)

    async def _search_result_callback(search_results: list[SearchResult] | None) -> None:
        if search_results or search_results is None:
            await REDIS.xadd(
                f"results_{job_id}", {"results": json.dumps(to_jsonable_python(search_results))}
            )
            with anyio.CancelScope(shield=True):
                await publish_searches(db, view_ctx)

    canceled = False

    async def run():
        nonlocal canceled
        try:
            async with db.advisory_lock(
                view_ctx.fg_id + "__search__" + query.search_query, action_id="mutation"
            ):
                await db.compute_search(
                    view_ctx,
                    query.search_query,
                    _search_result_callback,
                    read_only,
                )
        except:
            canceled = True
            raise
        finally:
            with anyio.CancelScope(shield=True):
                if canceled:
                    print(f"job {job_id} canceled")
                    await db.set_job_status(job_id, JobStatus.CANCELED)
                else:
                    print(f"job {job_id} completed")
                    await db.set_job_status(job_id, JobStatus.COMPLETED)

                await publish_searches(db, view_ctx)
                await REDIS.delete(f"results_{job_id}")

    async def await_commands():
        q = f"commands_{job_id}"

        while True:
            _queue, command = await REDIS.blpop(q)  # type: ignore
            logger.info(f"{job_id} received {command}")

            match command:  # type: ignore
                case "cancel":
                    # The search task may internally prevent cancellation requests from bubbling all
                    # the way up, so explicitly note down the cancellation if we do it ourselves.
                    nonlocal canceled
                    canceled = True

                    run_task.cancel()

    run_task = asyncio.create_task(run())
    commands_task = asyncio.create_task(await_commands())

    _, pending = await asyncio.wait([run_task, commands_task], return_when=asyncio.FIRST_COMPLETED)  # type: ignore
    for task in pending:
        task.cancel()

    logger.info(f"worker finishing job {job_id}")


async def compute_embeddings(ctx: dict[Any, Any], view_ctx: ViewContext, job_id: str):
    """
    Worker function to compute embeddings for agent runs.

    Args:
        ctx: Worker context (unused but required by arq)
        view_ctx: The view context containing frame grid information
        job_id: The ID of the embedding job
    """
    logger.info(f"Starting compute_embeddings: view_ctx={view_ctx}, job_id={job_id}")

    db = await DBService.init()
    job = await db.get_job(job_id)

    if job is None:
        logger.error(f"Embedding job {job_id} not found")
        return

    if job.type != "compute_embeddings":
        logger.error(f"Job {job_id} is not an embedding job (type: {job.type})")
        return

    should_index = job.job_json["should_index"]

    await db.set_job_status(job_id, JobStatus.RUNNING)

    # Track completion states
    embedding_completed = False
    indexing_completed = False

    async def _progress_callback(progress: int):
        """Callback for embedding computation progress"""
        progress_data = {
            "indexing_phase": "pending" if should_index else "not_required",
            "embedding_progress": progress,
            "indexing_progress": 0,
        }

        # Send via websocket instead of Redis stream
        await publish_framegrid_update(
            view_ctx.fg_id, {"action": "embedding_progress", "payload": progress_data}
        )

    async def _poll_indexing_status():
        nonlocal indexing_completed

        """Poll and report indexing progress after embeddings complete"""
        try:
            # Wait for embeddings to complete before starting to poll
            while not embedding_completed:
                await asyncio.sleep(2)

            # Now start polling for indexing progress
            while not indexing_completed:
                await asyncio.sleep(3)

                phase, percent = await db.get_indexing_progress(view_ctx.fg_id)
                if phase is None:
                    continue

                progress_data = {
                    "indexing_phase": phase,
                    "embedding_progress": 100,
                    "indexing_progress": percent or 0,
                }

                # Send via websocket instead of Redis stream
                await publish_framegrid_update(
                    view_ctx.fg_id, {"action": "embedding_progress", "payload": progress_data}
                )

                # If indexing is complete (100%), we can stop polling
                if percent is not None and percent >= 100:
                    indexing_completed = True
                    break

        except Exception as e:
            logger.error(f"Error polling indexing status for job {job_id}: {e}")
            # Don't re-raise here, let the main task handle failures

    async def run():
        """Main embedding computation logic"""
        nonlocal embedding_completed, indexing_completed

        try:
            async with db.advisory_lock(view_ctx.fg_id, action_id="compute_embeddings"):
                # Compute embeddings
                await db.compute_embeddings(view_ctx, _progress_callback)
                embedding_completed = True
                logger.info(f"Embeddings computation completed for job {job_id}")

            if should_index:
                # Report that we're starting indexing
                progress_data = {
                    "indexing_phase": "starting",
                    "embedding_progress": 100,
                    "indexing_progress": 0,
                }
                # Send via websocket instead of Redis stream
                await publish_framegrid_update(
                    view_ctx.fg_id, {"action": "embedding_progress", "payload": progress_data}
                )

                # Compute index
                await db.compute_ivfflat_index(view_ctx)
                indexing_completed = True
                logger.info(f"Indexing completed for job {job_id}")
            else:
                # No indexing needed
                indexing_completed = True

        except Exception as e:
            logger.error(f"Error computing embeddings for job {job_id}: {e}")
            raise

        finally:
            with anyio.CancelScope(shield=True):
                await db.set_job_status(job_id, JobStatus.COMPLETED)
                # Send completion message via websocket
                await publish_framegrid_update(
                    view_ctx.fg_id, {"action": "embedding_complete", "payload": {}}
                )

    # Create main computation task
    run_task = asyncio.create_task(run())

    # Create indexing poll task only if needed
    indexing_poll_task = None
    if should_index:
        indexing_poll_task = asyncio.create_task(_poll_indexing_status())

    try:
        # Wait for the main computation to complete
        await run_task

        # Wait for indexing poll task if it exists
        if indexing_poll_task:
            try:
                await indexing_poll_task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error(f"Error in embedding job {job_id}: {e}")
        # Cancel indexing poll task if it exists and is still running
        if indexing_poll_task and not indexing_poll_task.done():
            indexing_poll_task.cancel()
            try:
                await indexing_poll_task
            except asyncio.CancelledError:
                pass
        raise
    finally:
        logger.info(f"Worker finishing embedding job {job_id}")


def run():
    """Run a single worker that processes both search and embedding jobs."""

    assert REDIS_HOST is not None and REDIS_PORT is not None

    run_worker(
        {
            "functions": [compute_search, compute_embeddings],
            "redis_settings": RedisSettings(host=REDIS_HOST, port=int(REDIS_PORT)),
            "queue_name": "embedding_and_search_queue",
            "max_jobs": 5,  # Allow up to 5 concurrent jobs per worker
        }
    )
