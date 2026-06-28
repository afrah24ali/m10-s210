"""Multi-service coordinator — Stretch Thu (Honors Track)."""

import asyncio
import logging
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException

try:
    from coordinator.models import AnswerRequest, AnswerResponse
    from coordinator.upstream import call_upstream
except ModuleNotFoundError:
    from models import AnswerRequest, AnswerResponse
    from upstream import call_upstream


app = FastAPI(title="Stretch Thu — Multi-Service Coordinator")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("coordinator")


CLASSIFIER_URL = "http://classifier_svc:8001/classify"

SERVICE_URLS = {
    "nlp_svc": "http://nlp_svc:8002/extract",
    "kg_svc": "http://kg_svc:8003/kg/query",
    "rag_svc": "http://rag_svc:8004/rag/answer",
}


@app.post("/answer", response_model=AnswerResponse)
async def answer(req: AnswerRequest):
    """Classify → fan out → aggregate → respond."""

    start = time.perf_counter()

    async with httpx.AsyncClient() as client:
        try:
            clf_response = await client.post(
                CLASSIFIER_URL,
                json={"question": req.question},
                timeout=5.0,
            )
            clf_response.raise_for_status()

        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "classifier_unavailable",
                    "message": str(exc),
                },
            )

        clf_payload = clf_response.json()
        routes = clf_payload.get("routes", [])

        services_to_call = [
            route["service"]
            for route in routes
            if route.get("service") in SERVICE_URLS
        ]

        if not services_to_call:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "no_valid_routes",
                    "classifier_response": clf_payload,
                },
            )

        tasks = [
            call_upstream(
                service_name,
                SERVICE_URLS[service_name],
               {"question": req.question},
               timeout_s=10.0 if service_name == "rag_svc" else 5.0,


            )
            for service_name in services_to_call
        ]

        upstream_results = await asyncio.gather(*tasks)

    results: dict[str, Any] = {}
    responded: list[str] = []

    for result in upstream_results:
        if isinstance(result, dict):
            service = result.get("service")
            status = result.get("status")
            payload = result.get("payload")
        else:
            service = result.service
            status = result.status
            payload = result.payload

        if status == "ok" and service:
            results[service] = payload
            responded.append(service)

    partial = len(responded) < len(services_to_call)

    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    logger.info(
        {
            "event": "coordinator_request",
            "called": services_to_call,
            "responded": responded,
            "partial": partial,
            "latency_ms": latency_ms,
        }
    )

    if not responded:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "all_upstreams_failed",
                "called": services_to_call,
            },
        )

    return AnswerResponse(
        results=results,
        partial=partial,
        responded=responded,
    )


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "coordinator"}