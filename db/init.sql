-- Initial setup on a fresh db-server:
-- sudo -u postgres psql -d postgres -f db/init.sql
-- Run once. The password is requested interactively, not stored in Git.
\set ON_ERROR_STOP on

CREATE ROLE ml_app LOGIN;
\password ml_app
CREATE DATABASE ml_predictions;
\connect ml_predictions

CREATE TABLE predictions (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    input_data JSONB NOT NULL,
    prediction JSONB NOT NULL,
    model_version VARCHAR(50) NOT NULL
);

REVOKE CONNECT ON DATABASE ml_predictions FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE ml_predictions TO ml_app;
GRANT USAGE ON SCHEMA public TO ml_app;
GRANT SELECT, INSERT ON TABLE predictions TO ml_app;
GRANT USAGE ON SEQUENCE predictions_id_seq TO ml_app;
