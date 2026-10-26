import copy

import pytest

from logger_service import app as service


PAYLOAD = {
    "input_data": {"features": [
        14.23, 1.71, 2.43, 15.6, 127, 2.8, 3.06,
        0.28, 2.29, 5.64, 1.04, 3.92, 1065,
    ]},
    "prediction": {"class": 0, "probability": 0.99},
    "model_version": "wine-rf-v1",
}


def test_health():
    response = service.app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "service": "logger"}


def test_metrics_does_not_count_log_request():
    before = service.LOG_REQUESTS_TOTAL.labels(status="success")._value.get()
    response = service.app.test_client().get("/metrics")
    assert response.status_code == 200
    assert response.content_type.startswith("text/plain")
    assert b"logger_requests_total" in response.data
    assert b"logger_db_errors_total" in response.data
    assert service.LOG_REQUESTS_TOTAL.labels(status="success")._value.get() == before


@pytest.mark.parametrize("payload", [None, [], {}, {"input_data": {}, "prediction": {}}])
def test_invalid_payload_does_not_connect(monkeypatch, payload):
    def unexpected_connection():
        pytest.fail("Invalid input must not reach the database")

    monkeypatch.setattr(service, "get_db", unexpected_connection)
    before = service.LOG_REQUESTS_TOTAL.labels(status="bad_request")._value.get()
    response = service.app.test_client().post("/log", json=payload)
    assert response.status_code == 400
    assert service.LOG_REQUESTS_TOTAL.labels(status="bad_request")._value.get() == before + 1


@pytest.mark.parametrize("field,value", [
    ("features", [True] * 13), ("features", [float("inf")] * 13),
    ("features", [1, 2, 3, 4]), ("class", True), ("class", 3),
    ("probability", -0.1), ("probability", float("nan")),
    ("model_version", "x" * 51),
])
def test_invalid_wine_data(field, value):
    payload = copy.deepcopy(PAYLOAD)
    if field == "features":
        payload["input_data"][field] = value
    elif field == "model_version":
        payload[field] = value
    else:
        payload["prediction"][field] = value
    assert service.app.test_client().post("/log", json=payload).status_code == 400


def test_log_commits_and_returns_id(monkeypatch):
    events = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query, values):
            assert "RETURNING id" in query
            assert values[0].adapted == PAYLOAD["input_data"]
            assert values[1].adapted == PAYLOAD["prediction"]
            assert values[2] == PAYLOAD["model_version"]
            events.append("insert")

        def fetchone(self):
            return (39,)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("commit")

        def cursor(self):
            return Cursor()

        def close(self):
            events.append("close")

    monkeypatch.setattr(service, "get_db", lambda: Connection())
    before = service.LOG_REQUESTS_TOTAL.labels(status="success")._value.get()
    response = service.app.test_client().post("/log", json=PAYLOAD)
    assert response.status_code == 201
    assert response.get_json() == {"status": "logged", "id": 39}
    assert events == ["insert", "commit", "close"]
    assert service.LOG_REQUESTS_TOTAL.labels(status="success")._value.get() == before + 1


def test_database_failure_is_not_success(monkeypatch):
    def fail():
        raise service.psycopg2.OperationalError("Test connection failure")

    monkeypatch.setattr(service, "get_db", fail)
    errors = service.DB_WRITE_ERRORS._value.get()
    successes = service.LOG_REQUESTS_TOTAL.labels(status="success")._value.get()
    response = service.app.test_client().post("/log", json=PAYLOAD)
    assert response.status_code == 503
    assert "id" not in response.get_json()
    assert service.DB_WRITE_ERRORS._value.get() == errors + 1
    assert service.LOG_REQUESTS_TOTAL.labels(status="success")._value.get() == successes
