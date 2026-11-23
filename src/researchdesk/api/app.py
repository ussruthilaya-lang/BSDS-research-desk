"""Job API skeleton (M3 fills it in). For now it only answers GET /health."""
from fastapi import FastAPI

from researchdesk import contracts as c

app = FastAPI(title="researchdesk-api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "api", "contract_version": c.CONTRACT_VERSION}
