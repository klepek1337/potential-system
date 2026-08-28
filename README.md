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

An optional OpenAI layer adds sourced internet research and a portfolio-level decision report.
The deterministic scanner remains responsible for immediate SMA, stop and liquidation warnings.

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

Each plan can also declare its role and intended holding horizon:

```json
{
  "role": "core",
  "holding_horizon": "position_w1"
}
```

Allowed roles are `core` and `tactical`. Allowed horizons are `tactical_h4`, `swing_d1`,
`position_w1`, and `cycle`. Defaults are `core` and `swing_d1`. These fields prevent an H4
momentum warning from being misrepresented as an automatic exit from a multi-month core.

## Hierarchical decision state

The deterministic report separates market structure from position management:

| Layer | Input | Responsibility |
|---|---|---|
| Ribbon | SMA 20/50/120/200 order | Bullish, bearish, mixed, or insufficient structure |
| Momentum | Confirmed H4 close vs SMA 20 | Whether adding exposure remains allowed |
| H4 structure | Confirmed H4 close vs SMA 50 | Tactical health and escalation |
| Hard invalidation | Stop and explicit thesis level | Immediate deterministic action |

A confirmed H4 close through SMA 20 creates `MOMENTUM_WARNING`: the core remains `HOLD`,
while adding becomes `PAUSE_ADDS`. It is an early signal, not a complete opposite-side setup.
The opposite scenario requires a failed SMA 20 reclaim and a confirmed SMA 50 loss.

For tactical and D1 swing positions, a confirmed SMA 50 loss escalates to `THESIS_AT_RISK`
and `REDUCE_RISK`. For `position_w1` or `cycle` cores, the same event becomes
`EXECUTION_STRUCTURE_BROKEN`: H4 adding remains paused, but the application does not pretend
that H4 alone invalidated a W1 or cycle thesis. An explicit thesis level or hard stop still has
priority for every horizon.

The system marks price as `HOLDING_EXTENDED` without a fixed percentage threshold. It compares
the distance from price to SMA 20 with the current width of the SMA 20–SMA 50 band. This adapts
to the instrument instead of embedding a coin-specific magic number.

The report is intentionally not a one-sided signal. It never changes a position and does not
issue a hidden stop. Its deterministic position verdicts mean:

| Verdict | Meaning |
|---|---|
| `TRZYMAJ WG PLANU` | Price has not breached the configured thesis or stop |
| `NIE DOKŁADAJ DO STRATY` | Thesis is still active, but price is adverse versus entry |
| `RUCH ZDYSKWALIFIKOWANY` | Configured thesis support/resistance was breached |
| `STOP NARUSZONY` | Current price crossed the configured stop |
| `CEL OSIĄGNIĘTY` | Current price reached the configured target |
| `MOMENTUM_WARNING` | SMA 20 was lost; hold the core and pause additions |
| `THESIS_AT_RISK` | SMA 50 was lost for a tactical or D1 swing position |
| `EXECUTION_STRUCTURE_BROKEN` | H4 weakened, but a W1/cycle core needs strategic review |

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

## Optional AI research

The AI layer uses the official OpenAI Python SDK and the Responses API with hosted web search.
It receives prepared market and position snapshots, but never receives the OKX API credentials.
No order, margin, transfer or stop-modification tool is exposed to the model.

Enable it only after creating a separate OpenAI API key:

```env
AI_ANALYSIS_ENABLED=true
AI_DAILY_REPORT_LOCAL_TIME=08:05
AI_EVENT_REPORTS_ENABLED=true
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.5
OPENAI_REASONING_EFFORT=high
```

The OpenAI API is billed separately from a ChatGPT subscription. Keep the API key only in
`.env`; never commit it or send it to Telegram.

There are two report paths:

1. `daily` performs one portfolio-wide web research run. It covers the BTC/ETH relationship,
   dominance and market breadth, derivatives, ETF flows, on-chain evidence, macro liquidity,
   rates, inflation, the dollar, yields and material news.
2. `market_event` runs once per instrument scan when one or more SMA tests start or resolve. It
   compares the new event with the latest daily thesis rather than treating an SMA cross as a
   self-contained trading signal.

The model must return a strict JSON schema. The application then formats that result for
Telegram and splits messages at Telegram's length limit. Allowed position decisions are:

- `HOLD`
- `HOLD_DO_NOT_ADD`
- `REDUCE_RISK`
- `EXIT_THESIS_INVALIDATED`
- `TARGET_REACHED_REVIEW_PROFIT`
- `NO_EDGE`
- `INSUFFICIENT_DATA`

Reports and previous theses are stored in SQLite. A daily report therefore states what changed
instead of recreating an unrelated opinion each day. Web facts require a source URL; missing or
conflicting data must be reported explicitly.

Every AI market snapshot includes the deterministic ribbon, momentum, position phase,
`core_action`, `adding_action`, role, and holding horizon. The model may explain conflicts but
must not silently replace the hard state produced by the scanner.

The deterministic risk layer is deliberately independent. A failed or slow OpenAI request does
not suppress the original SMA alert. Event research is sent as a follow-up Telegram message.
OpenAI work runs in a bounded single-worker queue, so web research does not pause the OKX polling
loop and multiple events cannot launch unbounded parallel API calls.

Test one complete AI report without waiting for the configured daily time:

```bash
python -m ma_alert_bot --ai-report-now
```

Position risk is checked on every polling cycle, independently from AI:

```env
STOP_WARNING_DISTANCE_PERCENT=1.0
LIQUIDATION_WARNING_DISTANCE_PERCENT=5.0
```

The scanner sends a transition alert when price first enters one of these ranges or breaches the
configured stop. SQLite suppresses repeats while the same condition remains active and rearms
the alert after price leaves the risk range.

Official references:

- [OpenAI Responses web search](https://developers.openai.com/api/docs/guides/tools-web-search)
- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OKX API v5](https://www.okx.com/docs-v5/en/)

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
cp position_plans.example.json position_plans.json
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
- News and macro context require `AI_ANALYSIS_ENABLED=true` and a working OpenAI API key.
