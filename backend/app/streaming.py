import asyncio
from collections.abc import AsyncIterator
import anyio
from starlette.responses import StreamingResponse


class ClosingIterator:
    def __init__(self, source, on_close):
        self.source = aiter(source)
        self.on_close = on_close
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.closed:
            raise StopAsyncIteration
        try:
            return await anext(self.source)
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self):
        if self.closed:
            return
        self.closed = True
        with anyio.CancelScope(shield=True):
            try:
                await self.source.aclose()
            finally:
                self.on_close()


class ClosingStreamingResponse(StreamingResponse):
    def __init__(self, source, on_close, **kwargs):
        super().__init__(ClosingIterator(source, on_close), **kwargs)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # The turn reservation predates the first SSE byte, including failed headers.
            await self.body_iterator.aclose()


async def with_heartbeat(source: AsyncIterator[str], interval: float = 2.0, cancel: asyncio.Event | None = None) -> AsyncIterator[str]:
    iterator = aiter(source)
    queue = asyncio.Queue(maxsize=1)

    async def produce():
        try:
            async for item in iterator:
                await queue.put(('item', item))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await queue.put(('error', exc))
        finally:
            close = getattr(iterator, 'aclose', None)
            if close is not None:
                await close()
        await queue.put(('done', None))

    # One producer owns upstream async contexts for their entire lifetime.
    producer = asyncio.create_task(produce())
    pending = None
    cancellation = asyncio.create_task(cancel.wait()) if cancel is not None else None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(queue.get())
            waiting = {pending, producer}
            if cancellation is not None:
                waiting.add(cancellation)
            ready, _ = await asyncio.wait(waiting, timeout=interval, return_when=asyncio.FIRST_COMPLETED)
            if cancellation is not None and cancellation in ready:
                return
            if not ready:
                yield ': keep-alive\n\n'
                continue
            if producer in ready:
                producer.result()
            kind, item = await pending
            pending = None
            if kind == 'done':return
            if kind == 'error':raise item
            yield item
    finally:
        # ASGI disconnects use level cancellation; cleanup must still release the turn lock.
        with anyio.CancelScope(shield=True):
            if cancellation is not None:
                cancellation.cancel()
                await asyncio.gather(cancellation, return_exceptions=True)
            if pending is not None:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
