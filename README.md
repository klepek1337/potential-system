# OKX H4 SMA alerts for Telegram

Small read-only scanner that monitors configured OKX instruments on the `4H` interval.
It never places, edits, or closes orders.

The scanner watches `SMA 20`, `SMA 50`, `SMA 120`, and `SMA 200` and sends:

1. a startup notification and the current price plus all four SMA levels;
2. one alert when the live H4 candle first touches an average;
3. one resolution after that candle closes.

Each startup and SMA-event report can also include:

- a long scenario with confirmation and invalidation levels;
- a short scenario with confirmation and invalidation levels;
- a neutral structural state;
- a position-aware assessment that separates holding, not adding, a breached thesis,
  a breached stop, and a reached target.

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

Decision context is also enabled by default:

```env
SEND_DECISION_REPORTS=true
DAILY_DECISION_REPORT_LOCAL_TIME=08:00
```

The daily time is interpreted in `DISPLAY_TIMEZONE`. Leave it empty to disable the scheduled
daily report while retaining startup and SMA-event decision context. SQLite records each local
date and instrument, so a continuously running scanner sends at most one daily copy per coin.

## Position-aware reports

The safe default is a manual position plan. Copy the example and keep the real file outside Git:

```bash
cp position_plans.example.json position_plans.json
```

Then configure:

```env
POSITION_SOURCE=manual
POSITION_PLANS_PATH=position_plans.json
```

`direction` and `entry_price` are required for a manual open position. Stop, target,
thesis support/resistance and the text thesis are optional. If the file does not exist or
does not contain the scanned instrument, the report still presents both market scenarios but
does not invent a personal position.

The report is intentionally not a one-sided signal. It never changes a position and does not
issue a hidden stop. Its deterministic position verdicts mean:

| Verdict | Meaning |
|---|---|
| `TRZYMAJ WG PLANU` | Price has not breached the configured thesis or stop |
| `NIE DOKŁADAJ DO STRATY` | Thesis is still active, but price is adverse versus entry |
| `RUCH ZDYSKWALIFIKOWANY` | Configured thesis support/resistance was breached |
| `STOP NARUSZONY` | Current price crossed the configured stop |
| `CEL OSIĄGNIĘTY` | Current price reached the configured target |

### Optional automatic OKX position detection

Create an OKX API key with **Read** permission only. Do not grant Trade or Withdraw permissions.
Then choose one mode:

```env
# Exchange entry, direction, size, leverage, liquidation price and unrealized PnL.
POSITION_SOURCE=okx_read_only

# Same live OKX fields, with stop/target/thesis taken from position_plans.json.
POSITION_SOURCE=okx_with_manual_override

OKX_API_KEY=
OKX_API_SECRET=
OKX_API_PASSPHRASE=
```

The account client contains only the authenticated `GET /api/v5/account/positions` operation.
There is no code path for placing, editing or cancelling an order. OKX position data does not
reliably contain the user's complete thesis, so `okx_with_manual_override` is the recommended
automatic mode. Active exchange stop orders remain separate from position data; configure the
intended stop manually until explicit read-only stop-order reconciliation is implemented.

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
- Market scanning uses public OKX endpoints. Private position access is optional and read-only.
- It monitors only simple moving averages and H4 candles.
- It does not treat an intrabar touch as confirmation.
- It does not aggregate prices from other exchanges.
- It does not fetch news or macro context; the decision report is structural and position-aware.
