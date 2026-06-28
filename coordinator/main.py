"""Multi-service coordinator — Stretch Thu (Honors Track).

The coordinator exposes a single POST /answer endpoint. On each call it:
1. Calls the classifier service to identify which downstream service(s)
   should answer the question.
2. Fans out to the selected service(s) via httpx.AsyncClient with a
   per-call 5-second timeout.
3. Aggregates the responses and returns a single AnswerResponse.
4. If any upstream returns a 5xx or times out, the coordinator returns
   200 with `partial: true` and a per-service attribution payload —
   never a 5xx that would lose the working upstream's response.
"""
import asyncio
import logging
import time
import httpx
from fastapi import FastAPI,HTTPException
from pydantic import BaseModel
from models import AnswerRequest, AnswerResponse
from typing import Any
app = FastAPI(title="Stretch Thu — Multi-Service Coordinator")
logging.basicConfig(level=logging.INFO)
logger =logging.getLogger("coordinator")
CLASSIFIER_URL ="http://classifier_svc:8001/classify"

SERVICE_URLS = {
    "nlp_svc": "http://nlp_svc:8002/extract",
    "kg_svc": "http://kg_svc:8003/kg/query",
    "rag_svc": "http://rag_svc:8004/rag/answer",
}

@app.post("/answer", response_model=AnswerResponse)
async def answer(req: AnswerRequest):
    """Classify → fan out → aggregate → respond.

    Returns AnswerResponse. `partial: true` iff one or more upstreams
    failed or timed out.
    """
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
            call_upstream(client, service_name, req.question)
            for service_name in services_to_call
        ]

        upstream_results = await asyncio.gather(*tasks)

    results: dict[str, Any] = {}
    responded: list[str] = []

    for service_name, payload in upstream_results:
        if payload is not None:
            results[service_name] = payload
            responded.append(service_name)

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
async def call_upstream(
    client: httpx.AsyncClient,
    service_name: str,
    question: str,
) -> tuple[str, Any | None]:
    """Call one selected upstream service.

    Returns:
        (service_name, response_json) if successful
        (service_name, None) if failed or timed out
    """

    url = SERVICE_URLS.get(service_name)

    if url is None:
        return service_name, None

    timeout = 10.0 if service_name == "rag_svc" else 5.0

    try:
        response = await client.post(
            url,
            json={"question": question},
            timeout=timeout,
        )

        if response.status_code >= 500:
            return service_name, None

        response.raise_for_status()
        return service_name, response.json()

    except (httpx.TimeoutException, httpx.HTTPError):
        return service_name, None


