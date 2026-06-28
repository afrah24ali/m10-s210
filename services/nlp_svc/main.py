"""Mock downstream NLP service.

In the live stretch repo, this is replaced with the decomposed nlp_svc
that wraps the Lab's /extract endpoint. Here it ships as a minimal mock
the coordinator can fan out against while the learner authors the real
service body.
"""
from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(title="nlp_svc (mock)")
class ExtractRequest(BaseModel):
    question: str


@app.post("/extract")
def extract(req: ExtractRequest):
    words = req.question.split()

    entities = [
        {"text": word, "label": "ENTITY"}
        for word in words
        if word[:1].isupper()
    ]

    return {
        "service": "nlp_svc",
        "question": req.question,
        "entities":entities,
    }


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "nlp_svc"}
