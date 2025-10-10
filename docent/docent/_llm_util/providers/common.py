import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Literal, cast


@asynccontextmanager
async def async_timeout_ctx(timeout: float | None) -> AsyncIterator[None]:
    if timeout:
        async with asyncio.timeout(timeout):
            yield
    else:
        # No-op async contextmanager
        yield


def reasoning_budget(max_new_tokens: int, effort: Literal["low", "medium", "high"]) -> int:
    if effort == "high":
        ratio = 0.75
    elif effort == "medium":
        ratio = 0.5
    else:
        ratio = 0.25
    return int(max_new_tokens * ratio)


def coerce_tool_args(args: Any) -> dict[str, Any]:
    if isinstance(args, dict):
        return cast(dict[str, Any], args)
    if isinstance(args, str):
        try:
            loaded = json.loads(args)
            return (
                cast(dict[str, Any], loaded)
                if isinstance(loaded, dict)
                else {"__parse_error_raw_args": args}
            )
        except Exception:
            return {"__parse_error_raw_args": args}
    # Fallback: unknown structure
    return {"__parse_error_raw_args": str(args)}
