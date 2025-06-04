from docent._db_service.service import DBService


async def get_db() -> DBService:
    # DBService is a singleton, so we can just return the instance
    return await DBService.init()
