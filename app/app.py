import math
import os
import pickle
import time
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from flask import Flask, Response, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest,
)

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
LOGGER_URL = os.getenv("LOGGER_URL", "http://logger-service:5001/log")

with open(os.getenv("MODEL_PATH", "/model/model.pkl"), "rb") as file:
    model = pickle.load(file)

MODEL_VERSION = "wine-rf-v1"
REQUESTS_TOTAL = Counter(
    "ml_requests_total", "Prediction requests by HTTP status", ["status"]
)
PREDICTIONS_TOTAL = Counter(
    "ml_predictions_total", "Computed predictions regardless of logging outcome",
    ["model_version", "predicted_class"],
)
PREDICTION_LATENCY = Histogram(
    "ml_prediction_latency_seconds", "Full prediction request duration",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
LOGGER_ERRORS_TOTAL = Counter("ml_logger_errors_total", "Failed logger calls")
MODEL_INFO = Gauge("ml_model_info", "Loaded model version", ["version"])
MODEL_INFO.labels(version=MODEL_VERSION).set(1)
MODEL_ACCURACY = Gauge(
    "ml_model_accuracy", "Mean accuracy from stratified 5-fold cross-validation",
    ["model_version", "evaluation"],
)
evaluation_path = Path(os.getenv("MODEL_PATH", "/model/model.pkl")).with_name("evaluation.json")
if evaluation_path.exists():
    evaluation = json.loads(evaluation_path.read_text())
    MODEL_ACCURACY.labels(
        model_version=MODEL_VERSION, evaluation=evaluation["method"]
    ).set(evaluation["accuracy"])
for predicted_class in model.classes_:
    PREDICTIONS_TOTAL.labels(
        model_version=MODEL_VERSION, predicted_class=str(predicted_class)
    ).inc(0)


@app.before_request
def start_prediction_timer():
    if request.endpoint == "predict":
        g.prediction_started = time.perf_counter()


@app.after_request
def record_prediction_request(response):
    if request.endpoint == "predict":
        REQUESTS_TOTAL.labels(status=str(response.status_code)).inc()
        started = getattr(g, "prediction_started", None)
        if started is not None:
            PREDICTION_LATENCY.observe(time.perf_counter() - started)
    return response


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "prediction"})


@app.post("/predict")
def predict():
    data = request.get_json(silent=True)
    features = data.get("features") if isinstance(data, dict) else None

    if (
        not isinstance(features, list)
        or len(features) != model.n_features_in_
        or not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            for value in features
        )
    ):
        return jsonify({"error": "Provide 13 finite numeric features"}), 400

    result = {
        "class": int(model.predict([features])[0]),
        "probability": float(max(model.predict_proba([features])[0])),
    }

    PREDICTIONS_TOTAL.labels(
        model_version=MODEL_VERSION, predicted_class=str(result["class"])
    ).inc()
    payload = json.dumps({
        "input_data": {"features": features},
        "prediction": result,
        "model_version": MODEL_VERSION,
    }).encode("utf-8")
    log_request = urllib.request.Request(
        LOGGER_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    logged = False
    log_id = None
    try:
        with urllib.request.urlopen(log_request, timeout=8) as response:
            if response.status != 201:
                raise ValueError("Logger did not confirm creation")
            confirmation = json.loads(response.read(65536))
            if not isinstance(confirmation, dict):
                raise ValueError("Invalid logger confirmation")
            log_id = confirmation.get("id")
            if (
                confirmation.get("status") != "logged"
                or not isinstance(log_id, int)
                or isinstance(log_id, bool)
                or log_id <= 0
            ):
                raise ValueError("Invalid logger record id")
            logged = True
    except (urllib.error.URLError, OSError, ValueError):
        LOGGER_ERRORS_TOTAL.inc()
        app.logger.exception("Logger request failed; returning computed prediction")

    answer = {**result, "logged": logged}
    if logged:
        answer["log_id"] = log_id
        app.logger.info("Logger confirmed prediction id=%s", log_id)
    return jsonify(answer)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
