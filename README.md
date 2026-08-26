# OKX H4 SMA alerts for Telegram

Small read-only scanner that monitors configured OKX instruments on the `4H` interval.
It never places, edits, or closes orders.

The scanner watches `SMA 20`, `SMA 50`, `SMA 120`, and `SMA 200` and sends:

1. one alert when the live H4 candle first touches an average;
2. one resolution after that candle closes.

The result depends on the side from which price approached the average:

| Approach | H4 close | Result |
|---|---|---|
| From above | Above SMA | Support defended |
| From above | Below SMA | Support lost |
| From below | Below SMA | Resistance rejected price |
| From below | Above SMA | Resistance reclaimed |

## Why this is not a literal Pine translation

The supplied TradingView script only calculates and plots moving averages. This project adds
event state that Pine did not contain: approach direction, first-touch deduplication, persistence
across restarts, and resolution after the OKX candle reports `confirm=1`.

The current SMA uses the open candle's latest close, matching how an SMA moves on a live chart.
A touch means the current candle range contains the current SMA value:

```text
candle.low <= current_sma <= candle.high
```

## Setup

Requirements: Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

Edit `.env` and provide OKX instrument IDs. Examples:

```text
BTC-USDT       # spot
BTC-USDT-SWAP  # USDT perpetual swap
```

Start with `DRY_RUN=true`, which prints messages instead of sending them:

```bash
python -m ma_alert_bot --once
python -m ma_alert_bot
```

## Telegram

1. Create a bot using `@BotFather` and copy its token.
2. Send any message to the new bot.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `message.chat.id`.
4. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`.
5. Change `DRY_RUN=false`.

Never commit `.env` or paste the bot token into source code.

## Docker

```bash
cp .env.example .env
docker compose up --build -d
docker compose logs -f
```

SQLite state is stored under `data/`, mounted outside the container. Restarting the process does
not repeat an alert already registered for the same instrument, SMA, and H4 candle.

## Tests

```bash
python -m unittest discover -v
```

## Deliberate first-version limits

- Instruments are explicitly configured to prevent alert spam.
- The program uses public OKX endpoints and requires no OKX API key.
- It monitors only simple moving averages and H4 candles.
- It does not treat an intrabar touch as confirmation.
- It does not aggregate prices from other exchanges.
