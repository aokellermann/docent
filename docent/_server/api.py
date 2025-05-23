import time
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from docent._env_util import ENV
from docent._log_util import get_logger
from docent._server._broker.router import broker_router
from docent._server._rest.router import rest_router

logger = get_logger(__name__)


def get_allowed_origins() -> list[str]:
    """
    Get allowed CORS origins based on environment configuration.
    """
    # Check if specific origins are configured
    cors_origins = ENV.get("DOCENT_CORS_ORIGINS")
    if cors_origins:
        # Split comma-separated origins and strip whitespace
        origins = [origin.strip() for origin in cors_origins.split(",")]
        logger.info(f"Using configured CORS origins: {origins}")
        return origins

    # Default development origins
    default_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]
    logger.info(f"Using default development CORS origins: {default_origins}")
    return default_origins


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        # Log request details
        start_time = time.perf_counter()
        logger.highlight(f"Started {request.method} {request.url.path}")

        # Process the request
        response = await call_next(request)

        # Log completion time
        process_time = time.perf_counter() - start_time
        logger.highlight(
            f"Completed {request.method} {request.url.path} in {process_time * 1000:.2f}ms"
        )

        return response


asgi_app = FastAPI()
# Add request logging middleware first (before other middlewares)
asgi_app.add_middleware(RequestLoggingMiddleware)
asgi_app.add_middleware(
    CORSMiddleware,
    # we have to specify specific origins because we are making requests from the frontend
    # that include credentials (cookies). wildcard origins are not allowed.
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST router
asgi_app.include_router(rest_router, prefix="/rest")
asgi_app.include_router(broker_router, prefix="/broker")

# If running in production, add Sentry middleware
# import sentry_sdk
# from sentry_sdk.integrations.asgi import SentryAsgiMiddleware  # type: ignore
# if ENV.ENV_TYPE == "prod" or os.environ.get("ENABLE_SENTRY", False):
#     logger.info("Initializing Sentry for production")
#     sentry_sdk.init(  # type: ignore
#         dsn="https://c5f049f4a74b7cd17fbf688db7f4838a@o4509013218689024.ingest.us.sentry.io/4509013219803136",
#         # Add data like request headers and IP for users,
#         # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
#         send_default_pii=True,
#     )
#     asgi_app.add_middleware(SentryAsgiMiddleware)  # type: ignore


@asgi_app.get("/")
async def root():
    return "clarity has been achieved"


@asgi_app.get("/eval_ids")
async def get_eval_ids():
    # TODO(mengk): remove this deprecated endpoint
    return list[str]()
