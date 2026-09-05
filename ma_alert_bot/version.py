"""Application version and the release note shown on startup."""


CURRENT_VERSION = "1.7.0"
CURRENT_RELEASE_TITLE = "Analiza Szpont na żądanie"
CURRENT_RELEASE_CHANGES = (
    "komenda /szpont BTCUSDT analizuje zamknięte świece 1H, 2H, 4H i 1D",
    "H4 może zawetować pozorną synchronizację niższych interwałów",
    "raport pokazuje MACD histogram, zmianę względem ATR i strukturę SMA",
    "offset Telegrama jest zapisywany, więc komendy nie powtarzają się po restarcie",
)
