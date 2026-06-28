"""Mock downstream KG service."""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="kg_svc (mock)")

class KGQueryRequest(BaseModel):
    question: str

@app.post("/kg/query")
def kg_query(payload: KGQueryRequest):
     return {
        "service": "kg_svc",
        "question": payload.question,
        "answer": "KG service received the query. Real graph backend can be added here.",

        "cypher": "MATCH (n) RETURN n",
        "rows": [],
        "count": 0,
    }

@app.get("/healthz")
async def healthz():
    return {"status": "ok","service": "kg_svc",}
