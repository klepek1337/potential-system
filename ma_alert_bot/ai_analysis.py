import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from ma_alert_bot.decision_state import DecisionState
from ma_alert_bot.positions import PositionSnapshot


class AiDecision(StrEnum):
    HOLD = "HOLD"
    HOLD_DO_NOT_ADD = "HOLD_DO_NOT_ADD"
    REDUCE_RISK = "REDUCE_RISK"
    EXIT_THESIS_INVALIDATED = "EXIT_THESIS_INVALIDATED"
    TARGET_REACHED_REVIEW_PROFIT = "TARGET_REACHED_REVIEW_PROFIT"
    NO_EDGE = "NO_EDGE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AiReportType(StrEnum):
    DAILY = "daily"
    MARKET_EVENT = "market_event"


@dataclass(frozen=True)
class OkxDerivativeMetrics:
    last_price: float | None
    mark_price: float | None
    open_interest_contracts: float | None
    open_interest_currency: float | None
    funding_rate: float | None
    next_funding_rate: float | None
    next_funding_timestamp_ms: int | None
    twenty_four_hour_open_price: float | None
    twenty_four_hour_high_price: float | None
    twenty_four_hour_low_price: float | None
    twenty_four_hour_volume_currency: float | None


@dataclass(frozen=True)
class InstrumentMarketSnapshot:
    instrument_id: str
    generated_at_utc: str
    current_price: float
    latest_confirmed_h4_close: float
    h4_change_percent: float | None
    twenty_four_hour_change_percent: float | None
    moving_average_levels: dict[str, float]
    decision_state: DecisionState
    derivative_metrics: OkxDerivativeMetrics
    position: PositionSnapshot | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


AI_REPORT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "report_title": {"type": "string"},
        "market_regime": {"type": "string"},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "source_title": {"type": "string"},
                    "source_url": {"type": "string"},
                },
                "required": ["statement", "source_title", "source_url"],
                "additionalProperties": False,
            },
        },
        "inferences": {"type": "array", "items": {"type": "string"}},
        "long_case": {"type": "array", "items": {"type": "string"}},
        "short_case": {"type": "array", "items": {"type": "string"}},
        "position_decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "instrument_id": {"type": "string"},
                    "decision": {
                        "type": "string",
                        "enum": [decision.value for decision in AiDecision],
                    },
                    "rationale": {"type": "string"},
                    "do_not_add_reason": {"type": "string"},
                    "primary_danger": {"type": "string"},
                    "invalidation_condition": {"type": "string"},
                },
                "required": [
                    "instrument_id",
                    "decision",
                    "rationale",
                    "do_not_add_reason",
                    "primary_danger",
                    "invalidation_condition",
                ],
                "additionalProperties": False,
            },
        },
        "what_changed": {"type": "array", "items": {"type": "string"}},
        "strongest_signal": {"type": "string"},
        "biggest_risk": {"type": "string"},
        "no_action_condition": {"type": "string"},
        "data_gaps_or_conflicts": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "report_title",
        "market_regime",
        "facts",
        "inferences",
        "long_case",
        "short_case",
        "position_decisions",
        "what_changed",
        "strongest_signal",
        "biggest_risk",
        "no_action_condition",
        "data_gaps_or_conflicts",
    ],
    "additionalProperties": False,
}


AI_ANALYST_INSTRUCTIONS = """
Jesteś dwustronnym analitykiem ryzyka rynku kryptowalut dla właściciela pozycji futures.
Odpowiadasz po polsku. Nie wykonujesz transakcji i nie proponujesz zmiany zleceń przez API.

Najpierw przeszukaj internet. Priorytetowo korzystaj ze źródeł pierwotnych: regulatorów,
banków centralnych, urzędów statystycznych, emitentów ETF, dokumentacji projektów oraz
wiarygodnych dostawców danych. Ignoruj plotki, płatne promocje i powielone artykuły.

Oddziel fakty od wniosków. Każdy fakt z internetu musi zawierać prawdziwy URL źródła.
Dla faktu pochodzącego z wejściowego snapshotu wpisz source_title=OKX_API_SNAPSHOT oraz
source_url=OKX_API_SNAPSHOT. Nie wymyślaj danych, źródeł ani prawdopodobieństw.

Oceń równocześnie scenariusz LONG i SHORT. Uwzględnij: BTC, ETH, ETH/BTC, BTC dominance,
TOTAL/TOTAL2/TOTAL3, zmienność, funding, open interest, likwidacje, ETF flows, on-chain,
Fed, ECB, płynność, stopy, inflację, dolar, rentowności, credit spreads i istotne wiadomości.
Nie zakładaj altseason wyłącznie dlatego, że płynność lub ceny rosną.

Dla każdej pozycji oceń rzeczywisty stosunek pozostałego ryzyka do potencjału. Rozdziel
HOLD od dokładania ekspozycji. Dobra pozycja może zasługiwać na HOLD, ale jednocześnie
HOLD_DO_NOT_ADD. Snapshot zawiera deterministyczny decision_state. Traktuj SMA 20 jako
warstwę momentum i dokładania, a SMA 50 jako zdrowie struktury H4. Zamknięcie H4 pod SMA 20
dla longa albo nad SMA 20 dla shorta samo w sobie nie potwierdza odwrócenia trendu. Wymaga
nieudanego reclaimu i utraty SMA 50. Nie nadpisuj pól core_action ani adding_action własną
interpretacją bez jawnego wskazania konfliktu danych. Stop i ostrzeżenia o likwidacji z
aplikacji są nadrzędne wobec Twojej opinii. Unieważnienie tezy H4 wymaga potwierdzonego
zamknięcia, o ile skonfigurowany twardy stop nie został naruszony wcześniej.

Porównaj wynik z poprzednim raportem, jeśli został przekazany. W what_changed wpisz tylko
materialne zmiany. Jeśli brakuje danych albo źródła są sprzeczne, wskaż to jawnie.
Raport ma być zwięzły i decyzyjny: najwyżej sześć faktów, cztery wnioski oraz po trzy
argumenty dla LONG i SHORT. Nie nazywaj ruchu okazją, jeżeli informacja jest prawdopodobnie
wyceniona.
""".strip()


def build_ai_request_payload(
    report_type: AiReportType,
    snapshots: list[InstrumentMarketSnapshot],
    market_events: list[str],
    previous_report: dict[str, Any] | None,
) -> str:
    request_payload = {
        "report_type": report_type.value,
        "market_events": market_events,
        "market_snapshots": [snapshot.to_dict() for snapshot in snapshots],
        "previous_report": previous_report,
        "required_scope": {
            "daily": "pełny rynek, makro, wiadomości i wszystkie pozycje",
            "market_event": (
                "wpływ zdarzenia na poprzednią tezę oraz aktualną pozycję; "
                "nie powtarzaj całego raportu bez materialnej zmiany"
            ),
        }[report_type.value],
    }
    return json.dumps(request_payload, ensure_ascii=False, separators=(",", ":"))


def parse_ai_report(response_text: str) -> dict[str, Any]:
    parsed_report = json.loads(response_text)
    if not isinstance(parsed_report, dict):
        raise ValueError("OpenAI response must contain one JSON object")
    required_fields = set(AI_REPORT_JSON_SCHEMA["required"])
    missing_fields = required_fields.difference(parsed_report)
    if missing_fields:
        raise ValueError(
            "OpenAI report is missing fields: " + ", ".join(sorted(missing_fields))
        )
    for position_decision in parsed_report["position_decisions"]:
        AiDecision(position_decision["decision"])
    return parsed_report


def _format_bullets(items: list[str]) -> list[str]:
    return [f"• {item}" for item in items] if items else ["• Brak materialnej zmiany."]


def format_ai_report_for_telegram(report: dict[str, Any]) -> str:
    message_lines = [
        f"🤖 {report['report_title']}",
        "",
        f"Reżim: {report['market_regime']}",
        "",
        "FAKTY",
    ]
    for fact in report["facts"]:
        source = fact["source_title"]
        if fact["source_url"] != "OKX_API_SNAPSHOT":
            source = f"{source}: {fact['source_url']}"
        message_lines.append(f"• {fact['statement']} — {source}")

    message_lines.extend(["", "WNIOSKI", *_format_bullets(report["inferences"])])
    message_lines.extend(["", "SCENARIUSZ LONG", *_format_bullets(report["long_case"])])
    message_lines.extend(["", "SCENARIUSZ SHORT", *_format_bullets(report["short_case"])])

    for decision in report["position_decisions"]:
        message_lines.extend(
            [
                "",
                f"POZYCJA {decision['instrument_id']}: {decision['decision']}",
                f"• Powód: {decision['rationale']}",
                f"• Nie dokładaj, gdy: {decision['do_not_add_reason']}",
                f"• Ryzyko: {decision['primary_danger']}",
                f"• Unieważnienie: {decision['invalidation_condition']}",
            ]
        )

    message_lines.extend(
        [
            "",
            "CO SIĘ ZMIENIŁO",
            *_format_bullets(report["what_changed"]),
            "",
            f"Najmocniejszy sygnał: {report['strongest_signal']}",
            f"Największe ryzyko: {report['biggest_risk']}",
            f"Brak działania: {report['no_action_condition']}",
        ]
    )
    if report["data_gaps_or_conflicts"]:
        message_lines.extend(
            [
                "",
                "BRAKI LUB KONFLIKTY DANYCH",
                *_format_bullets(report["data_gaps_or_conflicts"]),
            ]
        )
    return "\n".join(message_lines)
