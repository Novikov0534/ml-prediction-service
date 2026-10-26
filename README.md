# ML Prediction Service

Учебный проект DevOps, лабораторная работа 8.

## Архитектура

Клиент → prediction-service:5000/predict → logger-service:5001/log → PostgreSQL.
ВМ102 (10.10.10.102): два Flask-сервиса и мониторинг.
ВМ100 (10.10.10.101): БД ml_predictions и резервные копии.
Модель Wine Random Forest использует 13 числовых признаков, три класса.

Prediction-service не содержит клиента PostgreSQL и не получает DB_PASSWORD.
LOGGER_URL=http://logger-service:5001/log. Logger проверяет JSON,
записывает предсказание транзакцией и возвращает HTTP 201 с id.
Health обоих сервисов проверяет процесс HTTP, не доступность PostgreSQL.

При отказе logger предсказание остаётся доступным (требование ЛР8):
HTTP 200, logged=false, рост ml_logger_errors_total. При подтверждённой
записи logged=true и log_id. Автоматические повторы не выполняются:
это предотвращает повторные записи после неоднозначного сетевого тайм-аута.
Очередь и гарантированная последующая доставка в учебном стенде отсутствуют.

## Локальная сборка на ВМ102

    docker build -f docker/Dockerfile -t prediction-service:lab8 .
    docker build -f docker/Dockerfile.logger -t logger-service:lab8 .
    PREDICTION_IMAGE=prediction-service:lab8 LOGGER_IMAGE=logger-service:lab8 docker compose -f docker/docker-compose.yml up -d --pull never --remove-orphans

Перед стартом нужны docker/.env (DB_PASSWORD) и monitoring/.monitoring.env
(GF_SECURITY_ADMIN_PASSWORD). Значения не сохраняются в Git.
На время разработки ml-deploy.timer отключён.
Постоянные тома мониторинга и настройки резервных копий сохранены.

## Проверки

    curl -fsS http://127.0.0.1:5000/health
    curl -fsS http://127.0.0.1:5001/health
    docker logs --tail 20 logger-service

POST /predict принимает {"features": [13 числовых значений]}.
POST /log: input_data.features, prediction.class, prediction.probability,
model_version. БД: public.predictions, результат возвращается как log_id.
Мониторинг описан в monitoring/README.md.

## CI и развёртывание

Workflow проверяет оба сервиса, обучает модель и выполняет тесты.
После push в main публикуются два образа prediction-service и logger-service
с тегами latest и SHA коммита. Оба образа собираются до начала публикации.
После первой публикации запускается ansible/app_playbook.yml:

    ansible-playbook -i ansible/inventory.ini ansible/app_playbook.yml --ask-become-pass

Плейбук загружает опубликованные образы и запускает весь стек,
затем проверяет оба /health. Требуются существующие файлы проекта и секреты.
Для таймера установите обновлённый docker/deploy.sh в /usr/local/sbin/ml-deploy
с правами 0755. Только после публикации обоих образов включите
ml-deploy.timer. Скрипт обновляет оба сервиса и проверяет их healthcheck.
Теги latest изменяемые; синхронная атомарная публикация пары не обеспечена.
Для воспроизведения конкретной сборки используйте одинаковый SHA в
PREDICTION_IMAGE и LOGGER_IMAGE.
