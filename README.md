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
