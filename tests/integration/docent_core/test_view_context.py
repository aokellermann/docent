import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from docent_core.docent.db.contexts import ViewContext
from docent_core.docent.db.filters import ComplexFilter, PrimitiveFilter
from docent_core.docent.db.schemas.auth_models import User
from docent_core.docent.db.schemas.label import SQLATag
from docent_core.docent.db.schemas.tables import SQLAAgentRun


@pytest.mark.asyncio
async def test_view_context_outer_join_preserves_runs_without_tags(
    db_session: AsyncSession,
    test_collection_id: str,
    test_user: User,
) -> None:
    run_with_tag = SQLAAgentRun(
        id="run-with-tag",
        collection_id=test_collection_id,
        name="with_tag",
        metadata_json={"foo": "bar"},
    )
    run_without_tag = SQLAAgentRun(
        id="run-without-tag",
        collection_id=test_collection_id,
        name="without_tag",
        metadata_json={"foo": "bar"},
    )
    db_session.add_all([run_with_tag, run_without_tag])
    await db_session.flush()
    db_session.add(
        SQLATag(
            id="tag-1",
            collection_id=test_collection_id,
            agent_run_id=run_with_tag.id,
            value="priority",
            created_by=test_user.id,
        )
    )
    await db_session.commit()

    base_filter = ComplexFilter(
        filters=[
            PrimitiveFilter(key_path=["tag"], value="priority", op="=="),
            PrimitiveFilter(key_path=["metadata", "foo"], value="bar", op="=="),
        ],
        op="or",
    )
    view_ctx = ViewContext(
        collection_id=test_collection_id,
        view_id="view-outer-join",
        user=None,
        base_filter=base_filter,
    )

    query = view_ctx.apply_base_filter(select(SQLAAgentRun))
    result = await db_session.execute(query)
    rows = result.scalars().all()

    assert {row.id for row in rows} == {run_with_tag.id, run_without_tag.id}
