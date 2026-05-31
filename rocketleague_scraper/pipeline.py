"""Shared async queue pipeline primitives."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from loguru import logger

T = TypeVar("T")


@dataclass(slots=True)
class PipelineResult:
    seen: int = 0
    written: int = 0


class QueuePipeline(Generic[T]):
    """Small queue worker pool with cancellation-safe shutdown."""

    def __init__(self, workers: int, handler: Callable[[T], Awaitable[int]]):
        self.queue: asyncio.Queue[T | None] = asyncio.Queue()
        self.workers = workers
        self.handler = handler
        self.result = PipelineResult()

    async def put(self, item: T) -> None:
        self.result.seen += 1
        await self.queue.put(item)

    async def run(self) -> None:
        tasks = [asyncio.create_task(self._worker(i), name=f"pipeline-worker-{i}") for i in range(self.workers)]
        await self.queue.join()
        for _ in tasks:
            await self.queue.put(None)
        await asyncio.gather(*tasks)

    async def _worker(self, index: int) -> None:
        while True:
            item = await self.queue.get()
            try:
                if item is None:
                    return
                self.result.written += await self.handler(item)
            except Exception:
                logger.exception("Pipeline worker {} failed for item", index)
            finally:
                self.queue.task_done()
