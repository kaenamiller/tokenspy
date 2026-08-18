from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import List

from . import store
from .adapters.base import Adapter
from .config import Config
from .schema import ProviderSnapshot

logger = logging.getLogger(__name__)


def _coerce_to_snapshot(adapter: Adapter, result: ProviderSnapshot | Exception) -> ProviderSnapshot:
    if isinstance(result, ProviderSnapshot):
        return result
    logger.error("Adapter %s raised unexpectedly: %s", adapter.id, result, exc_info=result)
    return ProviderSnapshot(
        id=adapter.id,
        display_name=adapter.display_name,
        status="parse_error",
        windows=[],
        last_polled_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        error=f"Unexpected error: {result}",
    )


async def poll_once(adapters: List[Adapter]) -> List[ProviderSnapshot]:
    results = await asyncio.gather(
        *(asyncio.wait_for(a.fetch(), timeout=30) for a in adapters),
        return_exceptions=True,
    )
    snapshots = [_coerce_to_snapshot(a, r) for a, r in zip(adapters, results)]
    store.write_state(snapshots)
    return snapshots


async def run_forever(config: Config, adapters: List[Adapter]) -> None:
    stagger = 2.0
    while True:
        logger.info("Starting poll cycle")
        results = []
        for i, adapter in enumerate(adapters):
            if i > 0:
                await asyncio.sleep(stagger)
            try:
                result = await asyncio.wait_for(adapter.fetch(), timeout=30)
            except Exception as exc:
                result = exc
            results.append(_coerce_to_snapshot(adapter, result))

        store.write_state(results)
        for snap in results:
            if snap.status == "ok":
                logger.info("%s: ok — %d windows", snap.id, len(snap.windows))
            else:
                logger.warning("%s: %s — %s", snap.id, snap.status, snap.error)

        await asyncio.sleep(config.poll_interval_seconds)
