import asyncio

import pytest

from app.streaming import with_heartbeat


def test_upstream_context_stays_in_one_task_across_all_yields():
    import anyio
    async def run():
        tasks=[]
        async def source():
            with anyio.CancelScope():
                for item in ('first','second'):
                    tasks.append(asyncio.current_task())
                    yield item
                tasks.append(asyncio.current_task())
        assert [item async for item in with_heartbeat(source())]==['first','second']
        assert len(set(tasks))==1
    asyncio.run(run())


def test_ready_data_does_not_wait_for_heartbeat_or_cancellation():
    async def run():
        async def source():
            yield 'first'
            yield 'second'
        async def collect():
            return [item async for item in with_heartbeat(source(),interval=60,cancel=asyncio.Event())]
        assert await asyncio.wait_for(collect(),0.25)==['first','second']
    asyncio.run(run())


def test_idle_heartbeats_do_not_interrupt_the_pending_upstream_event():
    async def run():
        release = asyncio.Event()
        closed = asyncio.Event()

        async def source():
            try:
                yield 'data: first\n\n'
                await release.wait()
                yield 'data: final\n\n'
            finally:
                closed.set()

        stream = with_heartbeat(source(), interval=0.01)
        try:
            assert await anext(stream) == 'data: first\n\n'
            assert await asyncio.wait_for(anext(stream), 1) == ': keep-alive\n\n'
            assert await asyncio.wait_for(anext(stream), 1) == ': keep-alive\n\n'
            assert not closed.is_set()
            release.set()
            assert await asyncio.wait_for(anext(stream), 1) == 'data: final\n\n'
            assert [item async for item in stream] == []
            assert closed.is_set()
        finally:
            await stream.aclose()

    asyncio.run(run())


def test_closing_after_a_heartbeat_cancels_and_closes_the_upstream():
    async def run():
        closed = asyncio.Event()

        async def source():
            try:
                await asyncio.sleep(3600)
                yield 'unreachable'
            finally:
                closed.set()

        stream = with_heartbeat(source(), interval=0.01)
        assert await asyncio.wait_for(anext(stream), 1) == ': keep-alive\n\n'
        assert not closed.is_set()
        await stream.aclose()
        assert closed.is_set()

    asyncio.run(run())


def test_disconnect_while_waiting_cleans_up_the_upstream_task():
    async def run():
        started = asyncio.Event()
        closed = asyncio.Event()

        async def source():
            try:
                started.set()
                await asyncio.sleep(3600)
                yield 'unreachable'
            finally:
                closed.set()

        stream = with_heartbeat(source(), interval=60)
        consumer = asyncio.create_task(anext(stream))
        await asyncio.wait_for(started.wait(), 1)
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer
        assert closed.is_set()

    asyncio.run(run())


def test_upstream_failure_is_propagated_after_a_heartbeat():
    async def run():
        release = asyncio.Event()
        closed = asyncio.Event()

        async def source():
            try:
                await release.wait()
                raise RuntimeError('upstream failure')
                yield 'unreachable'
            finally:
                closed.set()

        stream = with_heartbeat(source(), interval=0.01)
        assert await asyncio.wait_for(anext(stream), 1) == ': keep-alive\n\n'
        release.set()
        with pytest.raises(RuntimeError, match='upstream failure'):
            await anext(stream)
        assert closed.is_set()

    asyncio.run(run())


def test_ready_events_keep_their_order_and_end_without_extra_frames():
    async def run():
        async def source():
            yield 'data: delta\n\n'
            yield 'data: done\n\n'

        assert [item async for item in with_heartbeat(source())] == [
            'data: delta\n\n',
            'data: done\n\n',
        ]

    asyncio.run(run())
