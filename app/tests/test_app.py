import importlib
import json
import os
from pathlib import Path
import urllib.error

import pytest

os.environ["MODEL_PATH"] = str(Path(__file__).resolve().parents[2] / "model" / "model.pkl")
service = importlib.import_module("app.app")
FEATURES = [14.23, 1.71, 2.43, 15.6, 127, 2.8, 3.06, 0.28, 2.29, 5.64, 1.04, 3.92, 1065]


class Confirmation:
    status = 201

    def __init__(self, payload=None):
        self.payload = {"status": "logged", "id": 51} if payload is None else payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        return json.dumps(self.payload).encode()


def test_health():
    response = service.app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "service": "prediction"}


def test_metrics_exposes_prometheus_format():
    response = service.app.test_client().get("/metrics")
    assert response.status_code == 200
    assert response.content_type.startswith("text/plain")
    for name in (b"ml_predictions_total", b"ml_prediction_latency_seconds_bucket",
                 b"ml_model_info", b"ml_model_accuracy{", b"ml_logger_errors_total"):
        assert name in response.data


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


@pytest.mark.parametrize("features", [[], [1, 2, 3, 4], [True] * 13, [float("inf")] * 13])
def test_predict_rejects_invalid_features_without_http(monkeypatch, features):
    def unexpected_call(*args, **kwargs):
        pytest.fail("Invalid input must not call logger")

    monkeypatch.setattr(service.urllib.request, "urlopen", unexpected_call)
    response = service.app.test_client().post("/predict", json={"features": features})
    assert response.status_code == 400


def test_predict_calls_logger_without_database_credentials(monkeypatch):
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    captured = []

    def send(request, timeout):
        captured.append((request, timeout))
        return Confirmation()

    monkeypatch.setattr(service.urllib.request, "urlopen", send)
    counter = service.PREDICTIONS_TOTAL.labels(model_version="wine-rf-v1", predicted_class="0")
    before = counter._value.get()
    response = service.app.test_client().post("/predict", json={"features": FEATURES})
    assert response.status_code == 200
    result = response.get_json()
    assert result["class"] == 0 and result["logged"] is True and result["log_id"] == 51
    request, timeout = captured[0]
    assert request.get_method() == "POST"
    assert request.full_url == service.LOGGER_URL
    assert timeout == 8
    assert json.loads(request.data) == {
        "input_data": {"features": FEATURES},
        "prediction": {"class": result["class"], "probability": result["probability"]},
        "model_version": "wine-rf-v1",
    }
    assert counter._value.get() == before + 1
    assert len(captured) == 1


@pytest.mark.parametrize("error", [
    urllib.error.URLError("connection refused"), TimeoutError("timeout"),
    urllib.error.HTTPError("http://logger/log", 503, "Unavailable", {}, None),
])
def test_logger_failure_returns_prediction_without_claiming_storage(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(service.urllib.request, "urlopen", fail)
    before = service.LOGGER_ERRORS_TOTAL._value.get()
    response = service.app.test_client().post("/predict", json={"features": FEATURES})
    assert response.status_code == 200
    result = response.get_json()
    assert result["class"] == 0 and result["logged"] is False
    assert "log_id" not in result
    assert service.LOGGER_ERRORS_TOTAL._value.get() == before + 1


@pytest.mark.parametrize("confirmation", [[], {"status": "logged"}, {"status": "logged", "id": True}])
def test_invalid_confirmation_is_counted_as_logger_failure(monkeypatch, confirmation):
    monkeypatch.setattr(service.urllib.request, "urlopen", lambda *a, **k: Confirmation(confirmation))
    before = service.LOGGER_ERRORS_TOTAL._value.get()
    result = service.app.test_client().post("/predict", json={"features": FEATURES}).get_json()
    assert result["logged"] is False and "log_id" not in result
    assert service.LOGGER_ERRORS_TOTAL._value.get() == before + 1
