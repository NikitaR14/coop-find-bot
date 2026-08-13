# Безопасное внедрение рядом с действующим Telegram-ботом

Инструкция рассчитана на текущий сервер `176.124.218.55`: исходный бот находится в
`/root/telegram-bot/coop-find-bot`, служба называется `telegram-bot.service`.

## 1. Передача подготовленного релиза с Mac

На сервере:

```bash
mkdir -p /root/telegram-bot/releases/coopfind-20260812
```

На Mac:

```bash
cd /Users/nikita/Documents/coopfind
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude '.env' \
  --exclude '.DS_Store' --exclude 'var' \
  ./ root@176.124.218.55:/root/telegram-bot/releases/coopfind-20260812/
```

`--delete` применяется только к новому каталогу конкретного релиза. Рабочий каталог
Telegram-бота команда не затрагивает.

## 2. Резервные копии и окружение

На сервере:

```bash
mkdir -p /root/telegram-bot/backups/20260812
cd /root/telegram-bot/coop-find-bot
git diff > /root/telegram-bot/backups/20260812/server-changes.patch
cp -a dump.sql /root/telegram-bot/backups/20260812/dump-before-teamseek.sql

install -m 600 .env /root/telegram-bot/releases/coopfind-20260812/.env
mkdir -p /root/telegram-bot/media
nano /root/telegram-bot/releases/coopfind-20260812/.env
```

В `.env` сохранить все существующие значения и добавить или заменить только эти строки:

```dotenv
DISCORD_TOKEN=ВСТАВИТЬ_ТОКЕН_ИЗ_DISCORD_DEVELOPER_PORTAL
DISCORD_APPLICATION_ID=1537027262891823114
PRIMARY_GUILD_ID=1414672367476805794
DISCORD_STATS_WORKSHEET_NAME=Discord
MEDIA_DIR=/root/telegram-bot/media
WEBSITE_URL=https://gg.markets/s-TeamSeek
```

Права на секрет:

```bash
chmod 600 /root/telegram-bot/releases/coopfind-20260812/.env
```

В Discord Developer Portal для приложения должен быть включён `Server Members Intent`.

## 3. Новое виртуальное окружение и проверка

```bash
python3 -m venv /root/telegram-bot/venv-teamseek
/root/telegram-bot/venv-teamseek/bin/pip install --upgrade pip
/root/telegram-bot/venv-teamseek/bin/pip install -r /root/telegram-bot/releases/coopfind-20260812/requirements.txt

cd /root/telegram-bot/releases/coopfind-20260812
PYTHONPATH=src /root/telegram-bot/venv-teamseek/bin/python -m unittest discover -s tests -v
/root/telegram-bot/venv-teamseek/bin/alembic current
```

Сделать актуальную резервную копию PostgreSQL перед миграцией:

```bash
cd /root/telegram-bot/releases/coopfind-20260812
set -a
source .env
set +a
PGPASSWORD="$DB_PASSWORD" pg_dump \
  -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
  -Fc -f /root/telegram-bot/backups/20260812/database-before-teamseek.dump
```

## 4. Миграция и запуск двух служб

Миграция только добавляет поля, индексы и новые таблицы; существующие анкеты и оценки
не удаляются.

```bash
systemctl stop telegram-bot.service
cd /root/telegram-bot/releases/coopfind-20260812
/root/telegram-bot/venv-teamseek/bin/alembic upgrade head
/root/telegram-bot/venv-teamseek/bin/alembic current

ln -s /root/telegram-bot/releases/coopfind-20260812 /root/telegram-bot/current
install -d /etc/systemd/system/telegram-bot.service.d
install -m 644 deploy/telegram-bot.override.conf \
  /etc/systemd/system/telegram-bot.service.d/teamseek.conf
install -m 644 deploy/discord-bot.service /etc/systemd/system/discord-bot.service

systemctl daemon-reload
systemctl restart telegram-bot.service
systemctl enable --now discord-bot.service
```

Если `alembic upgrade head` завершился ошибкой, не продолжать переключение: выполнить
`systemctl start telegram-bot.service`, сохранить текст ошибки и вернуть старый сервис в
работу.

## 5. Проверка после запуска

```bash
systemctl --no-pager --full status telegram-bot.service discord-bot.service
journalctl -u telegram-bot.service -u discord-bot.service --since "10 minutes ago" --no-pager
```

Затем проверить вручную:

1. В Telegram открыть `@coopfind_bot` и убедиться, что старое меню работает.
2. В Discord выполнить `/menu`, `/form`, создать тестовую анкету и открыть `/all`.
3. Проверить, что Discord-анкета видна в Telegram и наоборот.
4. Создать AION 2 игрока и клан с сервером и фракцией.
5. Убедиться, что в Google Sheets появился отдельный лист `Discord`.

## Откат к прежнему Telegram-коду

Дополнительные поля БД старому коду не мешают, поэтому миграцию при обычном откате
не понижать.

```bash
systemctl stop discord-bot.service
ln -sfn /root/telegram-bot/coop-find-bot /root/telegram-bot/current
systemctl restart telegram-bot.service
systemctl --no-pager --full status telegram-bot.service
```
