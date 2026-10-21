# BRVM Stock AI Agent

BRVM Stock AI Agent provides market data, portfolio tools, and an AI assistant
for investors in the West African Regional Stock Exchange (BRVM). It includes a
Python backend/API, Telegram and WhatsApp integrations, and the Kora Bourse
Flutter app for Android and iOS.

## Backend

### Run locally

Requirements: Python 3.11+, an LLM backend such as Ollama, and the configuration
appropriate to the features you want to use.

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set `JWT_SECRET` in `.env` to enable mobile authentication. Configure the
selected LLM and any integrations in the same file, then start the API:

```bash
python -m scripts.run_api
```

The API listens on `http://localhost:8000` by default. API docs are available
at `/docs`. To run the Telegram bot and API together, use `python main.py`.

### Deploy or update with Docker Compose

On the server, create and configure `.env` from `.env.example`. Set a unique,
stable `JWT_SECRET` (for example, generate one with `openssl rand -hex 32`) to
enable mobile login. For email one-time codes, configure SMTP; do not use
`AUTH_PROVIDER=mock` in production.

Deploy the stack the first time:

```bash
./scripts/deploy.sh
```

After pulling code changes or editing `.env`:

```bash
./scripts/update.sh
```

The API is published on localhost by default; point a reverse proxy or Cloudflare
Tunnel at `http://localhost:8000`. Compose persists PostgreSQL and application
data in named volumes.

### Transfer existing local accounts and portfolios

The MiniMac's `app/data/brvm_bot.db` is SQLite; it cannot be copied directly into
the server's PostgreSQL database. The one-time importer below transfers accounts
(including password hashes), portfolios, watchlists, alerts, dividends, and
digest settings. It does not transfer chat history, market caches, OTP codes, or
active login sessions. Users will log in again on the server.

1. Stop the local API and other processes that write to the SQLite database.
   From the repository on the MiniMac, create a consistent SQLite backup:

   ```bash
   mkdir -p "$HOME/brvm-transfer"
   sqlite3 app/data/brvm_bot.db ".backup '$HOME/brvm-transfer/brvm_bot.sqlite3'"
   ```

2. Copy the backup to the server (replace the login and host):

   ```bash
   scp "$HOME/brvm-transfer/brvm_bot.sqlite3" user@server:~/brvm-transfer/
   ```

3. On the server, from the repository directory, back up PostgreSQL and stop
   services that could write user data:

   ```bash
   mkdir -p backups
   docker compose exec -T db pg_dump -U brvm -d brvm \
     > "backups/brvm-before-import-$(date +%Y%m%d-%H%M%S).sql"
   docker compose stop api bot
   ```

4. Run the importer in dry-run mode first. Review the table counts; if it reports
   a conflict or an error, stop and resolve it before applying:

   ```bash
   docker compose run --rm --no-deps \
     --entrypoint python \
     -v "$HOME/brvm-transfer:/transfer:ro" \
     api -m scripts.migrate_sqlite_to_postgres \
     --source /transfer/brvm_bot.sqlite3
   ```

5. If the dry run succeeds and the counts are expected, repeat with `--apply`,
   then restart the API and bot:

   ```bash
   docker compose run --rm --no-deps \
     --entrypoint python \
     -v "$HOME/brvm-transfer:/transfer:ro" \
     api -m scripts.migrate_sqlite_to_postgres \
     --source /transfer/brvm_bot.sqlite3 --apply
   docker compose up -d api bot
   ```

The importer preserves source IDs, skips rows that already match exactly, and
rolls back rather than overwriting conflicting target rows. It also creates
missing legacy `users` identity rows for imported app accounts and referenced
portfolio records when needed by foreign keys. Keep both backups until you have
verified that users can log in and their portfolios are present.

## Mobile app

The Flutter application is in [`mobile/`](mobile/README.md). It uses
`https://kbourse.neobytech.net` by default. From the mobile project directory:

```bash
cd mobile/brvm_mobile
flutter pub get
flutter run
```

For local development, override the API address with
`--dart-define=API_BASE_URL=http://<backend-host>:8000`. Build release packages
with `flutter build apk --release` or `flutter build appbundle --release`.

## Tests

Run the backend tests with `pytest`. Run Flutter tests from
`mobile/brvm_mobile` with `flutter test`.
