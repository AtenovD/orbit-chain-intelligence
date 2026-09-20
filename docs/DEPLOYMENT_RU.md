# Production-развёртывание MVP

## Где хранятся данные

| Данные | Хранилище | Защита |
|---|---|---|
| Пользователи, workspace, роли, агенты, команды, диалоги, события, задачи, Memory, отчёты | PostgreSQL 17, volume `postgres_data` | пароль БД, доступ только внутри Docker network, ежедневный `pg_dump` |
| Загруженные материалы | volume `orbit_files` | лимит 25 MB, безопасное имя, SHA-256, доступ через авторизованный workspace |
| API/OAuth/MCP-токены | PostgreSQL | Fernet-шифрование через обязательный `SECRET_ENCRYPTION_KEY`; ключ не хранится в БД |
| Веб-сессии | PostgreSQL | в БД только SHA-256 токена; срок по умолчанию 30 дней, отзыв из профиля |
| Пароли | PostgreSQL | `scrypt` с индивидуальной случайной солью; исходный пароль не сохраняется |

SQLite остаётся только локальным режимом разработки. Production compose всегда использует PostgreSQL и сначала выполняет `alembic upgrade head`.

## Минимальный VPS

- Ubuntu 24.04 LTS, 4 vCPU, 8 GB RAM, 80+ GB NVMe.
- Docker Engine + Compose plugin; наружу открыты только 22, 80 и 443.
- DNS: `A`/`AAAA` домена указывает на VPS. Caddy автоматически получает и обновляет TLS.
- Для реальных AI-запусков лучше отделить worker от web/API после первых 20–30 одновременных run.

## Первый запуск

1. Скопировать `.env.example` в `.env`.
2. Установить `DOMAIN`, `PUBLIC_URL=https://<domain>`, `CORS_ORIGINS=https://<domain>`.
   Если VPS уже использует порты 80/443, задать `API_BIND=127.0.0.1:<свободный порт>` и направить существующий reverse proxy на него.
3. Сгенерировать независимые длинные значения `POSTGRES_PASSWORD` и `SECRET_ENCRYPTION_KEY` (`Fernet.generate_key()`).
4. Настроить SMTP и `SMTP_FROM`. Без `SMTP_HOST` production продолжит обслуживать существующие аккаунты, но регистрация будет закрыта с `503` до создания пользователя: новые аккаунты не должны получать доступ без подтверждённого адреса.
5. Указать `ADMIN_EMAILS=owner@example.com` (можно несколько адресов через запятую). Только эти аккаунты увидят закрытый экран `/admin` с метриками и управлением доступом.
6. При необходимости указать `SENTRY_DSN` и `VITE_SENTRY_DSN` для двух отдельных Sentry-проектов: backend и browser. Без DSN Sentry отключён, остальная работа не меняется.
7. Запустить:

   ```sh
   docker compose -f compose.yaml -f compose.production.yaml up -d --build
   ```

8. Проверить `https://<domain>/api/v1/health` (в ответе есть `queue_depth`), регистрацию, подтверждение e-mail, вход, reset email и тестовый mock-run.

## Резервные копии

Запускать `scripts/backup.sh` ежедневно из cron и копировать архивы во внешнее S3-совместимое хранилище. Хранить минимум 14 ежедневных и 8 недельных копий. Раз в месяц выполнять тестовое восстановление в отдельную БД — backup без проверки восстановления не считается надёжным.

Пример cron на VPS (выполняется от `root`):

```cron
17 3 * * * ORBIT_PROJECT_DIR=/root/orbemind /root/orbemind/scripts/backup.sh >> /var/log/orbit-backup.log 2>&1
```

Копия на том же VPS не защищает от потери самого сервера. После `backup.sh` выгружайте свежий архив во внешний бакет:

```sh
apt-get install -y rclone && rclone config        # создать remote, например orbit-s3
```

```cron
47 3 * * * ORBIT_OFFSITE_REMOTE=orbit-s3:my-bucket/orbit /root/orbemind/scripts/offsite_backup.sh >> /var/log/orbit-backup.log 2>&1
```

`offsite_backup.sh` проверяет SHA256 перед загрузкой, только копирует (никогда не удаляет в бакете) и после загрузки сверяет байты через `rclone check`. Срок хранения задавайте lifecycle-правилом самого бакета. Ежемесячно запускайте `scripts/verify_backup.sh` — это реальное восстановление во временную БД.

## Ограничения публичного MVP

- Произвольные локальные `stdio` MCP отключены в production API: они требуют отдельного изолированного runner с allowlist, лимитами CPU/RAM и отсутствием доступа к сети/хосту по умолчанию.
- Приватные и loopback URL провайдеров блокируются, чтобы пользовательский connector не стал SSRF-прокси.
- Покупка домена и VPS не автоматизируется из репозитория: это платёж и выбор бренда владельцем. После выбора имени достаточно заполнить `.env` и DNS.
