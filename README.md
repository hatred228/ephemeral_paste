# ephemeral_paste

A self-hosted, lightweight, and secure self-destructing pastebin and secret sharing service in Python 3.

## Overview

`ephemeral_paste` lets you share sensitive credentials, API keys, passwords, and logs with zero third-party exposure. It stores secrets locally in SQLite and deletes them automatically after reading or upon timer expiration.

### Features

- **Burn on Read**: Secrets are wiped from database immediately upon the first view.
- **Configurable Expiration**: Choose between 1 view, 5 minutes, 1 hour, or 24 hours.
- **Zero Third-Party Dependencies**: Runs directly on standard Python 3.15.
- **REST API**: Easily create pastes directly via CLI / `curl`:

```powershell
curl -X POST http://127.0.0.1:8080/api/paste -H "Content-Type: application/json" -d "{\"content\": \"my_secret_token\", \"ttl\": \"burn\"}"
```

## Running the Server

```powershell
python server.py 8080
```
Then open `http://127.0.0.1:8080` in your web browser.

## License

MIT License
