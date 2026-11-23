import pytest
from fastapi.testclient import TestClient

from researchdesk import contracts as c
from researchdesk.api.app import app as api_app
from researchdesk.board.app import app as board_app
from researchdesk.workflow import worker


@pytest.mark.parametrize("app,name", [(api_app, "api"), (board_app, "board")])
def test_health(app, name):
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": name, "contract_version": c.CONTRACT_VERSION}


def test_worker_started_event():
    rec = worker.started_event(c.Settings(), "host-1")
    assert rec.event == "worker.started" and rec.worker_id == "host-1" and rec.fields["pid"]
