# Лабораторная работа 7

## Мониторинг на ВМ102
Стек: ML API, Prometheus, Node Exporter, Alertmanager,
Grafana и локальный получатель webhook-уведомлений.

Секреты: docker/.env содержит DB_PASSWORD,
monitoring/.monitoring.env содержит GF_SECURITY_ADMIN_PASSWORD.
Оба файла исключены из Git.

Сборка из корня проекта:
    docker build -f docker/Dockerfile -t ml-app:lab7 .

Запуск локального образа:
    ML_APP_IMAGE=ml-app:lab7 docker compose -f docker/docker-compose.yml up -d

Без ML_APP_IMAGE используется образ GHCR latest.
До публикации lab7 таймер ml-deploy.timer отключён.

Доступ через SSH-туннель:
Grafana — localhost:3000/d/ml-overview, логин admin.
Prometheus — localhost:9090/targets.
Alertmanager — localhost:9093.
Источник данных и дашборд Grafana загружаются автоматически.

## Метрики и оповещения
/metrics: запросы, успешные предсказания по классам,
задержка запросов, ошибки БД и информация о модели.
ml_model_accuracy — средняя точность стратифицированной
кросс-валидации по пяти разбиениям при сборке, не оценка дрейфа.

Правила: недоступность API, высокая задержка, низкая точность,
ошибки БД и отсутствие предсказаний.
Уведомления: docker logs --since 10m alert-receiver

Healthcheck проверяет /health.
restart: unless-stopped обеспечивает перезапуск при завершении процесса.
Статус unhealthy сам по себе контейнер не перезапускает.

## Резервные копии на ВМ100
Файлы конфигурации находятся в backup/.
Скрипт: /usr/local/sbin/ml-db-backup.
Каталог: /var/backups/ml-predictions, postgres, права 0700.
Служба ml-db-backup.service работает от postgres.
Таймер: ежедневно 02:00 Europe/Volgograd, Persistent=true.
Автоматические копии хранятся семь дней.
Формат custom, восстановление через pg_restore.
Ручная копия lab7_initial.dump исключена из автоматической ротации.
Восстановление проверено в базе ml_predictions_restore_lab7.
