# Мониторинг микросервисов ЛР8

Prometheus собирает четыре цели: prediction-service, logger-service,
node-exporter и prometheus. Интервал 15 секунд.
Grafana автоматически загружает datasource и JSON дашборда из этого каталога.
Дашборд /d/ml-overview содержит 12 панелей, включая запросы logger,
ошибки БД logger и ошибки HTTP-вызовов prediction → logger.

ml_predictions_total считает вычисленные предсказания, включая ответы
при отказе logger. Успешная запись отдельно учитывается
logger_requests_total{status="success"}. Счётчики обнуляются при рестарте.
ml_model_accuracy — результат 5-fold cross-validation при сборке,
не онлайн-оценка качества. Histogram охватывает весь /predict, включая HTTP.

Оповещения: MLServiceDown (prediction), LoggerServiceDown, LoggerErrors,
PredictionLoggerErrors, HighPredictionLatency, LowModelAccuracy,
NoPredictionsReceived. Уведомления принимает alert-receiver.
Команда: docker logs --since 10m alert-receiver

Порты привязаны к 127.0.0.1 ВМ102. Браузер подключается через SSH-туннель:
Grafana 3000, Prometheus 9090, Alertmanager 9093.
Секреты docker/.env и monitoring/.monitoring.env исключены из Git.

Резервное копирование на ВМ100 сохранено: ml-db-backup.timer ежедневно
в 02:00 Europe/Volgograd; автоматические дампы хранятся семь дней.
Скрипт и systemd units находятся в backup/.
