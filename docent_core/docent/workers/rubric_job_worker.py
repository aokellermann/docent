from docent_core._db_service.db import DocentDB
from docent_core.docent.db.contexts import ViewContext
from docent_core.docent.db.schemas.tables import SQLAJob
from docent_core.docent.services.llms import LLMService
from docent_core.docent.services.monoservice import MonoService
from docent_core.docent.services.rubric import RubricService
from docent_core.docent.services.usage import UsageService


async def rubric_job(ctx: ViewContext, job: SQLAJob):
    db = await DocentDB.init()
    mono_svc = await MonoService.init()
    async with db.session() as session:
        if ctx.user is None:
            raise ValueError("User is required to run a rubric job")

        usage_svc = UsageService(db.session)
        llm_svc = LLMService(db.session, ctx.user, usage_svc)
        rs = RubricService(session, db.session, mono_svc, llm_svc)

        await rs.run_rubric_job(ctx, job)
