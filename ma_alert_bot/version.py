"""Application version and the release note shown on startup."""


CURRENT_VERSION = "1.9.1"
CURRENT_RELEASE_TITLE = "Pełna synchronizacja nachylenia histogramów"
CURRENT_RELEASE_CHANGES = (
    "D1, H4, H2 i H1 muszą jednocześnie zwiększać histogram MACD",
    "ujemny histogram jest dozwolony, jeżeli konsekwentnie się odbudowuje",
    "dodatni, ale malejący histogram blokuje sygnał",
    "SMA H4 jest filtrem jakości A+, a nie blokadą wczesnej odbudowy",
)
