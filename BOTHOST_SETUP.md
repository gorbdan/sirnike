# Bothost setup

## Why the bot broke after "Update from Git"

BotHost rebuilds the Docker image from the Git repository and restarts the container. Files ignored by Git, such as `.env`, are not uploaded from your computer. Runtime data also should not live in the project root, because the root is replaced during Git deploys.

This project is configured for BotHost like this:

- dependencies are listed in `requirements.txt`;
- secrets are read from BotHost environment variables or local `.env`;
- SQLite database, logs, and generated outputs are stored under `DATA_DIR` (`/app/data` on BotHost).

## Environment variables to add in BotHost

Copy the real values from your local `.env` into the BotHost panel. Do not commit real tokens to Git.

Required:

```text
BOT_TOKEN=
IMGBB_API_KEY=
PROVIDER_TOKEN=
AI_PROVIDER=YESAPI
NANO_API_KEY=
```

If you use another provider, set `AI_PROVIDER` and the matching key instead:

```text
AI_PROVIDER=MASHAGPT
MASHAGPT_API_KEY=
```

or:

```text
AI_PROVIDER=ZVENO
ZVENO_API_KEY=
```

Recommended runtime paths:

```text
DATA_DIR=/app/data
BOT_LOG_DIR=/app/data
```

Optional settings are documented in `.env.example`.

## Deploy checklist

1. Commit and push these files to Git.
2. In BotHost, add the environment variables above.
3. Click "Update from Git".
4. Open runtime logs. A missing variable will be shown as `Missing required environment variable: NAME`.
5. If you already have a production `syrochnik.db`, upload it to BotHost as `/app/data/syrochnik.db` before starting the bot.
