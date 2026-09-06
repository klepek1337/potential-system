"""Application version and the release note shown on startup."""


CURRENT_VERSION = "1.9.2"
CURRENT_RELEASE_TITLE = "Radar D1 z historią 60 dni"
CURRENT_RELEASE_CHANGES = (
    "radar D1 wymaga 60 zamiast 202 zamkniętych świec",
    "dla krótszej historii D1 używane są dostępne SMA20 i SMA50",
    "instrumenty z historią krótszą niż 60 dni są pomijane bez tracebacku",
    "1H, 2H i 4H nadal wymagają pełnych 202 świec",
)
