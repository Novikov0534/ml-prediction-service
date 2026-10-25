import importlib
import os
from pathlib import Path

import pytest

os.environ["MODEL_PATH"] = str(
    Path(__file__).resolve().parents[2] / "model" / "model.pkl"
)
service = importlib.import_module("app.app")


def test_health():
    response = service.app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_metrics_exposes_prometheus_format():
    response = service.app.test_client().get("/metrics")
    assert response.status_code == 200
    assert response.content_type.startswith("text/plain")
    assert b"# HELP ml_predictions_total" in response.data
    assert b"ml_prediction_latency_seconds_bucket" in response.data
    assert b"ml_model_info" in response.data
    assert b"ml_model_accuracy{" in response.data


def test_metrics_scrape_is_not_counted_as_prediction():
    from prometheus_client import REGISTRY

    count = REGISTRY.get_sample_value("ml_prediction_latency_seconds_count")
    before = service.REQUESTS_TOTAL.labels(status="400")._value.get()
    client = service.app.test_client()
    client.get("/metrics")
    assert REGISTRY.get_sample_value("ml_prediction_latency_seconds_count") == count
    client.post("/predict", json={"features": []})
    assert service.REQUESTS_TOTAL.labels(status="400")._value.get() == before + 1
    assert REGISTRY.get_sample_value("ml_prediction_latency_seconds_count") == count + 1


def test_database_failure_is_counted(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "test-only")
    before = service.DB_ERRORS_TOTAL._value.get()

    def fail_connection(**kwargs):
        raise service.psycopg2.OperationalError("test-only failure")

    monkeypatch.setattr(service.psycopg2, "connect", fail_connection)
    response = service.app.test_client().post(
        "/predict", json={"features": [1.0] * 13}
    )
    assert response.status_code == 503
    assert service.DB_ERRORS_TOTAL._value.get() == before + 1


@pytest.mark.parametrize("features", [[], [1, 2, 3, 4], [True] * 13])
def test_predict_rejects_invalid_features(features):
    response = service.app.test_client().post(
        "/predict", json={"features": features}
    )
    assert response.status_code == 400


def test_predict_saves_result(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "test-only")
    saved = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query, values):
            saved.append(values)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(
        service.psycopg2, "connect", lambda **kwargs: Connection()
    )
    features = [
        14.23, 1.71, 2.43, 15.6, 127, 2.8, 3.06,
        0.28, 2.29, 5.64, 1.04, 3.92, 1065,
    ]
    response = service.app.test_client().post(
        "/predict", json={"features": features}
    )

    assert response.status_code == 200
    assert response.get_json()["class"] in (0, 1, 2)
    assert len(saved) == 1
    assert saved[0][2] == "wine-rf-v1"
