# OKX H4 SMA alerts for Telegram

Small read-only scanner that monitors configured OKX instruments on the `4H` interval.
It never places, edits, or closes orders.

The scanner watches `SMA 20`, `SMA 50`, `SMA 120`, and `SMA 200` and sends:

1. a startup notification and the current price plus all four SMA levels;
2. one alert when the live H4 candle first touches an average;
3. one resolution after that candle closes.

An optional one-minute layer also detects sharp ATR-normalized changes in the slope of SMA 20.
See [`docs/minute-sma-tilt.md`](docs/minute-sma-tilt.md). It is an informational micro-momentum
warning and does not execute any trading action.

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

The default `0.1%` margin also counts a near-touch. In other words, the candle range only needs
to intersect the area from `SMA - 0.1%` to `SMA + 0.1%`. Configure it in `.env`:

```env
MOVING_AVERAGE_TOUCH_MARGIN_PERCENT=0.1
```

Startup reporting is enabled by default and can be disabled independently:

```env
SEND_STARTUP_SUMMARY=false
```

## Setup

Requirements: Python 3.11 or newer.

### One-command Windows setup and update

Download `install-and-run.ps1`, then run it from PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install-and-run.ps1
```

The script clones or safely fast-forwards the latest `main`, creates `.venv`, installs dependencies,
runs the test suite, and starts the bot. It preserves `.env`, `data/positions.json`, and the SQLite
database. It stops instead of overwriting a repository containing local changes.

Optional parameters:

```powershell
.\install-and-run.ps1 -InstallDirectory "D:\Cryptostrata"
.\install-and-run.ps1 -RunOnce
.\install-and-run.ps1 -SkipTests
```

Release history is maintained in [`CHANGELOG.md`](CHANGELOG.md).

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

## Position-risk modules

- [Manual position registry](docs/manual-positions.md)
- [Configurable EMA levels](docs/ema-levels.md)
- [Dominant EMA stop anchor](docs/dominant-ema-stop.md)
- [Unrealized profit protection](docs/profit-protection.md)
- [Complete architecture](docs/system-overview.md)

All risk outputs are advisory. The project uses no authenticated trading endpoint and cannot place,
edit, reduce, or close a position.

## Deliberate first-version limits

- Instruments are explicitly configured to prevent alert spam.
- The program uses public OKX endpoints and requires no OKX API key.
- Original touch alerts monitor only simple moving averages and H4 candles; EMA risk analysis is a
  separate advisory layer.
- It does not treat an intrabar touch as confirmation.
- It does not aggregate prices from other exchanges.
