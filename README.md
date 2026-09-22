# OKX H4 SMA alerts for Telegram

Small read-only scanner that monitors configured OKX instruments on the `4H` interval.
It never places, edits, or closes orders.

The scanner watches `SMA 20`, `SMA 50`, `SMA 120`, and `SMA 200` and sends:

1. a startup notification and the current price plus all four SMA levels;
2. one alert when the live H4 candle first touches an average;
3. one resolution after that candle closes.

An optional one-minute layer also detects sharp ATR-normalized changes in the slope of SMA 200.
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

Current SMA/EMA level messages at startup are controlled separately and disabled by default:

```env
SEND_STARTUP_SUMMARY=true
SEND_STARTUP_CONFIGURATION=false
SEND_STARTUP_LEVEL_SUMMARIES=false
```

This combination sends only the version and latest update before normal monitoring begins. Set
`SEND_STARTUP_CONFIGURATION=true` to include active settings. Set
`SEND_STARTUP_LEVEL_SUMMARIES=true` to restore every instrument's current SMA/EMA levels after
startup.

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
.\install-and-run.ps1 -LocalChangesAction Stash
.\install-and-run.ps1 -LocalChangesAction Discard
```

When tracked or non-ignored local changes exist, the launcher asks whether to abort, store them in
`git stash`, or discard them. `Discard` resets tracked files and removes only untracked files that
are not ignored by Git. The ignored `.env`, `.venv`, `data/positions.json`, and SQLite database are
preserved. The same choice can be supplied non-interactively with `-LocalChangesAction`.

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

### Analiza Szpont na żądanie

Po uruchomieniu bota wyślij w skonfigurowanym czacie lub kanale:

```text
/szpont BTCUSDT
```

Możesz również użyć `/szpont BTC-USDT` albo pełnego identyfikatora
`/szpont BTC-USDT-SWAP`. Bot pobierze z OKX zamknięte świece `1H`, `2H`, `4H`
i `1D`, a następnie zwróci:

- kierunek oraz zmianę histogramu MACD na każdym interwale;
- zmianę histogramu znormalizowaną przez ATR;
- układ SMA 20/50/100/200 i opadające średnie znajdujące się nad ceną;
- stan synchronizacji, w tym osobne `H4 veto`.

Komendy są przyjmowane wyłącznie z `TELEGRAM_CHAT_ID`. Dla kanału Telegram bot musi
być jego administratorem, aby otrzymywać `channel_post`. Obsługę można wyłączyć:

```env
TELEGRAM_COMMANDS_ENABLED=false
```

Minimalna zmiana histogramu względem ATR jest jawnie konfigurowalna. Mniejsze ruchy
są klasyfikowane jako kompresja zamiast kierunkowego sygnału:

```env
SZPONT_MINIMUM_NORMALIZED_HISTOGRAM_SLOPE=0.001
```

Analiza jest informacyjna i nie korzysta z uwierzytelnionych endpointów transakcyjnych.

### Long Watch i dodawanie instrumentów bez restartu

```text
/obserwujlong BTCUSDT
/dodaj BCHUSDT
```

`/obserwujlong` zapisuje obserwację w SQLite i ustawia bieżące zamknięte świece jako
punkt bazowy. Od kolejnych zamknięć `1H`, `2H`, `4H` i `1D` wysyła alert tylko wtedy,
gdy dany histogram przechodzi ze stanu niespadającego w spadający. Kontynuacja spadku
na następnej świecy nie generuje duplikatu; po odbudowie kolejny zwrot w dół ponownie
uruchamia alert.

Alert pokazuje:

- MACD, Signal oraz ich różnicę — ta różnica jest histogramem;
- zmianę histogramu znormalizowaną przez ATR;
- odległość ceny od SMA20 w procentach i ATR;
- wzrost ceny od początku bieżącej dodatniej nogi MACD;
- percentyl histogramu z ostatnich 100 świec i ocenę przegrzania;
- stan pozostałych interwałów oraz zalecenie ochrony zysku.

`/dodaj` sprawdza instrument na publicznym API OKX i natychmiast dopisuje go do
aktywnego skanera. Nie modyfikuje pliku `.env`: runtime zapisuje dodatkowe symbole
w `STATE_DATABASE_PATH`, dzięki czemu zmiana działa bez restartu i przetrwa restart.
`/obserwujlong` również automatycznie dodaje instrument do aktywnego skanera.

Interwał sprawdzania obserwacji można ustawić w `.env`:

```env
LONG_WATCH_SCAN_INTERVAL_SECONDS=60
```

Komendy są advisory-only. Bot nie ma dostępu do prywatnego API OKX i nie może
zamknąć pozycji, wykonać wypłaty ani złożyć zlecenia.

### Radar wszystkich perpetual

Co godzinę, 90 sekund po zamknięciu świecy, bot pobiera tę samą listę aktywnych
perpetual USDT z OKX. Nadal odrzuca instrumenty z małym obrotem, szerokim spreadem
albo historią krótszą niż 60 dni. Dla pozostałych punktuje LONG i SHORT niezależnie.

Kierunek histogramu jest liczony na zamkniętych `1H`, `2H`, `4H` oraz na `1D LIVE`,
gdzie aktualna cena zastępuje tymczasowe zamknięcie bieżącej świecy dziennej.
Minimum to dwa zgodne interwały. Punkty synchronizacji: 2 TF = 4, 3 TF = 7,
4 TF = 10, plus maksymalnie 2 punkty za ciągłe pary `1H+2H`, `2H+4H`, `4H+1D`.
Interwał może wejść do synchronizacji LONG wyłącznie wtedy, gdy MACD i signal line
są poniżej zera, a histogram rośnie. Dla SHORT obowiązuje lustrzany filtr: MACD
i signal line muszą być powyżej zera, a histogram musi maleć. Sama zmiana histogramu
bez właściwego położenia obu linii jest traktowana jako brak kwalifikacji na tym TF.

Struktura wejścia jest liczona na `1H` dla SMA20/50/100/200:

- ekstremalna bliskość ceny do SMA: do 0,10% = 3 pkt, do 0,25% = 2 pkt,
  do 0,50% = 1 pkt;
- wsparcie/opór, test knotem i respekt korpusem: maksymalnie 3 pkt;
- klaster 2/3/4 SMA w odległości do 0,50%: 1/2/3 pkt;
- przecięcia 2/3/4 SMA w ostatnich 3 świecach: 1/2/3 pkt;
- przebicie ceną 2 albo 3–4 SMA: 1 albo 2 pkt;
- utrzymanie po przecięciu: 1–2 pkt, natychmiastowe zanegowanie: −2 pkt.

Łączny wynik ma maksymalnie 28 punktów: `WEAK` 4–8, `VALID` 9–13,
`GOOD` 14–18, `STRONG` 19–23, `A+ FULL SYNC` 24–28. `STRONG` wymaga
co najmniej jednego potwierdzenia strukturalnego SMA i nie może powstać wyłącznie
z histogramu. Telegram przepuszcza wyłącznie setupy od 9 punktów wzwyż, czyli
`VALID`, `GOOD`, `STRONG` i `A+ FULL SYNC`. Wyniki `WEAK` pozostają obliczane,
ale są odrzucane przed zbudowaniem raportu.

Stan jest zapisywany w SQLite. Ten sam symbol i ten sam poziom nie są ponownie
wysyłane; brak setupu nie generuje wiadomości. Wszystkie nowe setupy z jednego
skanu trafiają do raportu zbiorczego (dzielonego tylko przy limicie Telegrama).

Progi można ustawić w `.env`:

```env
MARKET_RADAR_ENABLED=true
MARKET_RADAR_MINIMUM_24H_NOTIONAL_USDT=5000000
MARKET_RADAR_MAXIMUM_SPREAD_PERCENT=0.30
MARKET_RADAR_MINIMUM_LISTING_AGE_DAYS=60
MARKET_RADAR_CANDLE_CONFIRMATION_DELAY_SECONDS=90
MARKET_RADAR_REQUEST_DELAY_SECONDS=0.12
```

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
