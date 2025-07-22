from typing import Any

from pydantic import BaseModel
from sqlalchemy.inspection import inspect as sqla_inspect

from docent._log_util import get_logger
from docent_core._db_service.contexts import ViewContext
from docent_core._db_service.service import MonoService
from docent_core._server._broker.redis_client import (
    publish_to_broker,
    publish_view_update,
)

logger = get_logger(__name__)


class CollectionDimension(BaseModel):
    """A dimension for organizing agent runs."""

    id: str
    name: str
    search_query: str | None = None
    metadata_key: str | None = None
    maintain_mece: bool | None = None
    loading_clusters: bool = False
    loading_bins: bool = False
    binIds: list[dict[str, Any]] | None = None


async def publish_base_filter(db: MonoService, ctx: ViewContext):
    await publish_view_update(
        ctx.collection_id,
        ctx.view_id,
        {
            "action": "base_filter",
            "payload": ctx.base_filter,
        },
    )


async def publish_searches(mono_svc: MonoService, ctx: ViewContext):
    await publish_view_update(
        ctx.collection_id,
        ctx.view_id,
        {
            "action": "searches",
            "payload": await mono_svc.get_searches_with_result_counts(ctx),
        },
    )


async def publish_agent_runs(mono_svc: MonoService, ctx: ViewContext):
    """Publish agent run IDs for the view"""

    # Get all agent run IDs for this view
    all_agent_run_ids = await mono_svc.get_agent_run_ids(ctx)

    payload: dict[str, Any] = {
        "request_type": "comb_stats",
        "result": {
            "agentRunIds": all_agent_run_ids,
        },
    }
    await publish_view_update(
        ctx.collection_id,
        ctx.view_id,
        {
            "action": "specific_bins",
            "payload": payload,
        },
    )

    return


async def publish_collections(mono_svc: MonoService):
    """Publish updated collections to all connected clients."""
    sqla_collections = await mono_svc.get_collections()
    collections = [
        # Get all columns from the SQLAlchemy object
        {c.key: getattr(obj, c.key) for c in sqla_inspect(obj).mapper.column_attrs}
        for obj in sqla_collections
    ]

    await publish_to_broker(
        None,  # Broadcast to the general channel
        {
            "action": "collections_updated",
            "payload": collections,
        },
    )


async def publish_homepage_state(mono_svc: MonoService, ctx: ViewContext):
    """Publish homepage state for a specific view. Always requires ViewProvider since base filters are view-scoped."""

    await publish_base_filter(mono_svc, ctx)
    await publish_agent_runs(mono_svc, ctx)
    await publish_searches(mono_svc, ctx)
