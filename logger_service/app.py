import logging
import math
import os

import psycopg2
from flask import Flask, Response, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from psycopg2.extras import Json

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

LOG_REQUESTS_TOTAL = Counter(
    "logger_requests_total", "Log requests by outcome", ["status"]
)
DB_WRITE_ERRORS = Counter("logger_db_errors_total", "Database write failures")
for outcome in ("success", "bad_request", "error"):
    LOG_REQUESTS_TOTAL.labels(status=outcome).inc(0)


def finite_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def valid_payload(data):
    if not isinstance(data, dict):
        return False
    input_data = data.get("input_data")
    prediction = data.get("prediction")
    version = data.get("model_version")
    if not isinstance(input_data, dict) or not isinstance(prediction, dict):
        return False
    features = input_data.get("features")
    predicted_class = prediction.get("class")
    probability = prediction.get("probability")
    return (
        isinstance(features, list)
        and len(features) == 13
        and all(finite_number(value) for value in features)
        and isinstance(predicted_class, int)
        and not isinstance(predicted_class, bool)
        and predicted_class in (0, 1, 2)
        and finite_number(probability)
        and 0 <= probability <= 1
        and isinstance(version, str)
        and 0 < len(version) <= 50
        and bool(version.strip())
    )


def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "10.10.10.101"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "ml_predictions"),
        user=os.getenv("DB_USER", "ml_app"),
        password=os.environ["DB_PASSWORD"],
        sslmode=os.getenv("DB_SSLMODE", "require"),
        connect_timeout=5,
    )


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "logger"})


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)


@app.post("/log")
def log():
    data = request.get_json(silent=True)
    if not valid_payload(data):
        LOG_REQUESTS_TOTAL.labels(status="bad_request").inc()
        return jsonify({"error": "Provide Wine features, prediction and model_version"}), 400

    try:
        connection = get_db()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO predictions (input_data, prediction, model_version)
                           VALUES (%s, %s, %s) RETURNING id""",
                        (Json(data["input_data"]), Json(data["prediction"]), data["model_version"]),
                    )
                    new_id = cursor.fetchone()[0]
        finally:
            connection.close()
    except psycopg2.Error:
        DB_WRITE_ERRORS.inc()
        LOG_REQUESTS_TOTAL.labels(status="error").inc()
        app.logger.exception("Database insert failed")
        return jsonify({"error": "Database unavailable"}), 503

    LOG_REQUESTS_TOTAL.labels(status="success").inc()
    app.logger.info("Prediction logged id=%s model_version=%s", new_id, data["model_version"])
    return jsonify({"status": "logged", "id": new_id}), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
