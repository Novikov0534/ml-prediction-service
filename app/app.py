import math
import os
import pickle

import psycopg2
from psycopg2.extras import Json
from flask import Flask, jsonify, request

app = Flask(__name__)

with open(os.getenv("MODEL_PATH", "/model/model.pkl"), "rb") as file:
    model = pickle.load(file)


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
        app.logger.exception("Database insert failed")
        return jsonify({"error": "Database unavailable"}), 503

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
