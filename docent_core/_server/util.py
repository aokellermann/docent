import json
from typing import Any, AsyncIterator, Awaitable, Callable

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from pydantic_core import to_jsonable_python


async def callback_streams_to_generator(
    execute: Callable[[], Awaitable[None]],
    send_stream: MemoryObjectSendStream[Any],
    recv_stream: MemoryObjectReceiveStream[Any],
):
    async def _execute_and_close_stream():
        await execute()
        await send_stream.aclose()

    async with anyio.create_task_group() as tg:
        tg.start_soon(_execute_and_close_stream)

        async for payload in recv_stream:
            yield payload


async def generator_to_sse_stream(
    generator: AsyncIterator[Any],
):
    async for payload in generator:
        data = json.dumps(to_jsonable_python(payload))
        yield f"data: {data}\n\n"

    yield "data: [DONE]\n\n"


def sse_stream(
    execute: Callable[[], Awaitable[None]],
    send_stream: MemoryObjectSendStream[Any],
    recv_stream: MemoryObjectReceiveStream[Any],
) -> AsyncIterator[str]:
    """Return an async iterator suitable for StreamingResponse content.

    This is intentionally a regular function (not async) so calling it returns
    an AsyncIterator immediately, which FastAPI accepts as StreamingResponse content.
    """

    generator = callback_streams_to_generator(execute, send_stream, recv_stream)
    return generator_to_sse_stream(generator)
