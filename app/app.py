import math
import os
import pickle
import time
import json
from pathlib import Path

import psycopg2
from psycopg2.extras import Json
from flask import Flask, Response, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest,
)

app = Flask(__name__)

with open(os.getenv("MODEL_PATH", "/model/model.pkl"), "rb") as file:
    model = pickle.load(file)

MODEL_VERSION = "wine-rf-v1"
REQUESTS_TOTAL = Counter(
    "ml_requests_total", "Prediction requests by HTTP status", ["status"]
)
PREDICTIONS_TOTAL = Counter(
    "ml_predictions_total", "Predictions successfully saved to the database",
    ["model_version", "predicted_class"],
)
PREDICTION_LATENCY = Histogram(
    "ml_prediction_latency_seconds", "Full prediction request duration",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
DB_ERRORS_TOTAL = Counter("ml_db_errors_total", "Database write failures")
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
    return jsonify({"status": "ok"})


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

    try:
        connection = psycopg2.connect(
            host=os.getenv("DB_HOST", "10.10.10.101"),
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("DB_NAME", "ml_predictions"),
            user=os.getenv("DB_USER", "ml_app"),
            password=os.environ["DB_PASSWORD"],
            sslmode=os.getenv("DB_SSLMODE", "require"),
            connect_timeout=5,
        )
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO predictions
                           (input_data, prediction, model_version)
                           VALUES (%s, %s, %s)""",
                        (Json({"features": features}), Json(result), "wine-rf-v1"),
                    )
        finally:
            connection.close()
    except psycopg2.Error:
        DB_ERRORS_TOTAL.inc()
        app.logger.exception("Database insert failed")
        return jsonify({"error": "Database unavailable"}), 503

    PREDICTIONS_TOTAL.labels(
        model_version=MODEL_VERSION, predicted_class=str(result["class"])
    ).inc()
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
