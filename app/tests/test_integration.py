import importlib
import os
from pathlib import Path
import threading

from werkzeug.serving import make_server

from logger_service import app as logger

os.environ["MODEL_PATH"] = str(Path(__file__).resolve().parents[2] / "model" / "model.pkl")
prediction = importlib.import_module("app.app")


def test_prediction_sends_real_http_and_logger_stores_payload(monkeypatch):
    saved = []
    events = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query, values):
            assert "INSERT INTO predictions" in query
            saved.append(values)

        def fetchone(self):
            return (123,)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("committed")

        def cursor(self):
            return Cursor()

        def close(self):
            events.append("closed")

    monkeypatch.setattr(logger, "get_db", lambda: Connection())
    server = make_server("127.0.0.1", 0, logger.app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(prediction, "LOGGER_URL", f"http://127.0.0.1:{server.server_port}/log")
    features = [14.23, 1.71, 2.43, 15.6, 127, 2.8, 3.06, 0.28, 2.29, 5.64, 1.04, 3.92, 1065]
    try:
        response = prediction.app.test_client().post("/predict", json={"features": features})
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
    result = response.get_json()
    assert response.status_code == 200
    assert result["class"] == 0 and result["logged"] is True and result["log_id"] == 123
    assert len(saved) == 1
    assert saved[0][0].adapted == {"features": features}
    assert saved[0][1].adapted == {"class": result["class"], "probability": result["probability"]}
    assert saved[0][2] == "wine-rf-v1"
    assert events == ["committed", "closed"]
