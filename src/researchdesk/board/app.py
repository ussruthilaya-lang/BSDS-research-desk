"""Live control room skeleton (M12 fills it in). For now it only answers GET /health."""
from fastapi import FastAPI

from researchdesk import contracts as c

app = FastAPI(title="researchdesk-board")


@app.get("/health")
def health():
    return {"status": "ok", "service": "board", "contract_version": c.CONTRACT_VERSION}
