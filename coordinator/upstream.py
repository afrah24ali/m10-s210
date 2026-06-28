"""httpx.AsyncClient helpers — per-call timeout enforcement."""

import asyncio
import logging
import time
from typing import Any

import httpx

from coordinator.models import UpstreamResult


logger = logging.getLogger("coordinator.upstream")


async def call_upstream(
    service: str,
    url: str,
    payload: dict,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Call one upstream service with per-call timeout enforcement."""

    start = time.perf_counter()
    client = httpx.AsyncClient()

    try:
        response = await asyncio.wait_for(
            client.post(url, json=payload),
            timeout=timeout_s,
        )

        status_code = getattr(response, "status_code", 200)

        if status_code >= 500:
            result = UpstreamResult(
                service=service,
                status="error",
                payload=None,
                error=f"upstream returned {status_code}",
            )
        else:
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()

            result = UpstreamResult(
                service=service,
                status="ok",
                payload=response.json(),
                error=None,
            )

    except (asyncio.TimeoutError, httpx.TimeoutException):
        result = UpstreamResult(
            service=service,
            status="timeout",
            payload=None,
            error="upstream timed out",
        )

    except httpx.HTTPError as exc:
        result = UpstreamResult(
            service=service,
            status="error",
            payload=None,
            error=str(exc),
        )

    finally:
        close = getattr(client, "aclose", None)
        if close is not None:
            await close()

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    result.latency_ms = latency_ms

    logger.info(
        {
            "event": "upstream_call",
            "service": result.service,
            "status": result.status,
            "timeout_s": timeout_s,
            "latency_ms": latency_ms,
        }
    )

    return result.model_dump()