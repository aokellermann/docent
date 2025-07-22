import pytest

from docent_core._db_service.schemas.auth_models import User
from docent_core._db_service.service import MonoService
from docent_core.services.charts import ChartsService


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_chart(
    mono_service: MonoService, charts_service: ChartsService, test_user: User, test_collection: str
):
    view_ctx = await mono_service.get_default_view_ctx(test_collection, test_user)

    await charts_service.create_chart(
        ctx=view_ctx,
        name="test_chart",
        series_key="test_series_key",
        x_key="test_x_key",
        y_key="test_y_key",
        chart_type="test_chart_type",
        rubric_filter="test_rubric_filter",
    )
