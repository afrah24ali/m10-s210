from typing import Any, Literal

from pydantic import BaseModel


class AnswerRequest(BaseModel):
    question: str


class AnswerResponse(BaseModel):
    results: dict[str, Any]
    partial: bool
    responded: list[str]


class UpstreamResult(BaseModel):
    service: str
    status: Literal["ok", "error", "timeout"]
    payload: Any | None = None
    error: str | None = None
    latency_ms: float | None = None