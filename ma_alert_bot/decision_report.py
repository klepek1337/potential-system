from collections.abc import Mapping

from ma_alert_bot.decision_state import (
    CoreAction,
    DecisionState,
    PositionPhase,
    RibbonState,
    build_decision_state,
)
from ma_alert_bot.positions import PositionDirection, PositionSnapshot


RATIO_TO_PERCENT_MULTIPLIER = 100.0


def _format_price(price: float) -> str:
    return f"{price:.10f}".rstrip("0").rstrip(".")


def _nearest_level_below(
    current_price: float,
    moving_average_levels: Mapping[int, float],
) -> tuple[int, float] | None:
    levels_below = [
        (period, value)
        for period, value in moving_average_levels.items()
        if value <= current_price
    ]
    return max(levels_below, key=lambda level: level[1], default=None)


def _nearest_level_above(
    current_price: float,
    moving_average_levels: Mapping[int, float],
) -> tuple[int, float] | None:
    levels_above = [
        (period, value)
        for period, value in moving_average_levels.items()
        if value > current_price
    ]
    return min(levels_above, key=lambda level: level[1], default=None)


def _format_level(level: tuple[int, float] | None) -> str:
    if level is None:
        return "brak kolejnej SMA w obserwowanym zestawie"
    period, value = level
    return f"SMA {period} ({_format_price(value)})"


def build_two_sided_scenario_lines(
    current_price: float,
    moving_average_levels: Mapping[int, float],
    position: PositionSnapshot | None,
    decision_state: DecisionState,
) -> list[str]:
    momentum_level = decision_state.momentum_level
    structural_level = decision_state.structural_level
    if (
        decision_state.ribbon_state is RibbonState.FULL_BULLISH
        and momentum_level is not None
        and structural_level is not None
    ):
        return [
            "⚖️ Scenariusze dwustronne",
            "LONG — obrona momentum: "
            f"SMA 20 ({_format_price(momentum_level)}); główna obrona H4: "
            f"SMA 50 ({_format_price(structural_level)}).",
            "LONG — potwierdzenie: utrzymanie pełnego bullish ribbonu; "
            "dokładanie dopiero po potwierdzonej obronie lub retestcie.",
            "SHORT — sygnał wstępny: zamknięcie H4 pod SMA 20; "
            "potwierdzenie: nieudany reclaim SMA 20 i zamknięcie H4 pod SMA 50.",
            "SHORT — unieważnienie: odzyskanie SMA 20; samo naruszenie SMA 20 "
            "nie odwraca strategicznego trendu.",
            "NEUTRAL — utrata SMA 20 przy utrzymaniu SMA 50 oznacza korektę, "
            "nie pełne potwierdzenie shorta.",
        ]
    if (
        decision_state.ribbon_state is RibbonState.FULL_BEARISH
        and momentum_level is not None
        and structural_level is not None
    ):
        return [
            "⚖️ Scenariusze dwustronne",
            "SHORT — obrona momentum: "
            f"SMA 20 ({_format_price(momentum_level)}); główna obrona H4: "
            f"SMA 50 ({_format_price(structural_level)}).",
            "SHORT — potwierdzenie: utrzymanie pełnego bearish ribbonu; "
            "dokładanie dopiero po potwierdzonym odrzuceniu lub retestcie.",
            "LONG — sygnał wstępny: zamknięcie H4 nad SMA 20; "
            "potwierdzenie: nieudana utrata SMA 20 i zamknięcie H4 nad SMA 50.",
            "LONG — unieważnienie: ponowna utrata SMA 20; samo naruszenie SMA 20 "
            "nie odwraca strategicznego trendu.",
            "NEUTRAL — odzyskanie SMA 20 przy pozostaniu pod SMA 50 oznacza "
            "odbicie, nie pełne potwierdzenie longa.",
        ]

    nearest_support = _nearest_level_below(current_price, moving_average_levels)
    nearest_resistance = _nearest_level_above(current_price, moving_average_levels)

    support_price = (
        position.thesis_support_price
        if position is not None and position.thesis_support_price is not None
        else nearest_support[1] if nearest_support is not None else None
    )
    resistance_price = (
        position.thesis_resistance_price
        if position is not None and position.thesis_resistance_price is not None
        else nearest_resistance[1] if nearest_resistance is not None else None
    )

    long_defense = (
        f"utrzymanie {_format_price(support_price)}"
        if support_price is not None
        else "brak zdefiniowanego wsparcia"
    )
    long_confirmation = (
        f"zamknięcie H4 nad {_format_price(resistance_price)}"
        if resistance_price is not None
        else "utrzymanie ceny nad całym ribbonem SMA"
    )
    short_confirmation = (
        f"zamknięcie H4 pod {_format_price(support_price)}"
        if support_price is not None
        else "brak potwierdzenia w obserwowanym zestawie SMA"
    )
    short_invalidation = (
        f"zamknięcie H4 nad {_format_price(resistance_price)}"
        if resistance_price is not None
        else "utrzymanie ceny nad całym ribbonem SMA"
    )

    averages_below_price = sum(
        moving_average_value <= current_price
        for moving_average_value in moving_average_levels.values()
    )
    if not moving_average_levels:
        neutral_state = "brak pełnych danych do oceny struktury"
    elif averages_below_price == len(moving_average_levels):
        neutral_state = "przewaga strukturalna long; short wymaga utraty wsparcia"
    elif averages_below_price == 0:
        neutral_state = "przewaga strukturalna short; long wymaga odzyskania oporu"
    else:
        neutral_state = (
            "struktura mieszana; cena między "
            f"{_format_level(nearest_support)} i {_format_level(nearest_resistance)}"
        )

    return [
        "⚖️ Scenariusze dwustronne",
        f"LONG — obrona: {long_defense}; potwierdzenie: {long_confirmation}.",
        f"SHORT — potwierdzenie: {short_confirmation}; unieważnienie: {short_invalidation}.",
        f"NEUTRAL — {neutral_state}.",
    ]


def _distance_percent(current_price: float, reference_price: float) -> float:
    return (
        (current_price - reference_price)
        / reference_price
        * RATIO_TO_PERCENT_MULTIPLIER
    )


def build_position_assessment_lines(
    current_price: float,
    latest_confirmed_price: float,
    position: PositionSnapshot | None,
    decision_state: DecisionState,
) -> list[str]:
    if position is None:
        return [
            "📌 Twoja pozycja: brak skonfigurowanej lub wykrytej pozycji.",
            "Decyzja: OBSERWUJ — scenariusz rynkowy bez personalizacji pozycji.",
        ]

    price_change_percent = _distance_percent(current_price, position.entry_price)
    signed_position_result = (
        price_change_percent
        if position.direction is PositionDirection.LONG
        else -price_change_percent
    )

    stop_breached = False
    if position.direction is PositionDirection.LONG:
        stop_breached = (
            position.stop_loss_price is not None
            and current_price <= position.stop_loss_price
        )
    else:
        stop_breached = (
            position.stop_loss_price is not None
            and current_price >= position.stop_loss_price
        )

    if stop_breached:
        verdict = "STOP NARUSZONY — teza pozycji wymaga natychmiastowego przeglądu."
    elif decision_state.core_action is CoreAction.REVIEW_PROFIT:
        verdict = "CEL OSIĄGNIĘTY — oceń realizację zysku zgodnie z planem."
    elif decision_state.core_action is CoreAction.EXIT:
        verdict = "RUCH ZDYSKWALIFIKOWANY — naruszono poziom tezy."
    elif decision_state.core_action is CoreAction.REDUCE_RISK:
        verdict = (
            "STRUKTURA H4 ZAGROŻONA — SMA 50 została naruszona; "
            "oceń redukcję ryzyka."
        )
    elif decision_state.position_phase is PositionPhase.EXECUTION_STRUCTURE_BROKEN:
        verdict = (
            "TRZYMAJ RDZEŃ, WSTRZYMAJ DOKŁADANIE — struktura wykonawcza H4 "
            "została naruszona, ale długi horyzont wymaga osobnego przeglądu W1."
        )
    elif decision_state.position_phase is PositionPhase.MOMENTUM_WARNING:
        verdict = (
            "TRZYMAJ RDZEŃ, WSTRZYMAJ DOKŁADANIE — utracono momentum SMA 20, "
            "ale SMA 50 nadal broni struktury H4."
        )
    elif signed_position_result < 0:
        verdict = "TEZA JESZCZE AKTYWNA, ALE NIE DOKŁADAJ DO STRATY."
    elif decision_state.position_phase is PositionPhase.HOLDING_EXTENDED:
        verdict = (
            "TRZYMAJ, NIE DOKŁADAJ — cena jest rozciągnięta względem pasma "
            "SMA 20–SMA 50."
        )
    else:
        verdict = "TRZYMAJ WG PLANU — brak naruszenia stopu lub tezy."

    lines = [
        f"📌 Twoja pozycja: {position.direction.value.upper()} "
        f"od {_format_price(position.entry_price)}",
        f"Wynik od wejścia: {signed_position_result:+.2f}%.",
        f"Decyzja: {verdict}",
    ]
    if position.stop_loss_price is not None:
        lines.append(f"Stop: {_format_price(position.stop_loss_price)}")
    else:
        lines.append("Stop: brak danych — raport nie zakłada ukrytego stopu.")
    if position.target_price is not None:
        lines.append(f"Cel: {_format_price(position.target_price)}")
    if position.liquidation_price is not None:
        lines.append(f"Likwidacja OKX: {_format_price(position.liquidation_price)}")
    if position.thesis:
        lines.append(f"Teza: {position.thesis}")
    return lines


def build_system_state_lines(decision_state: DecisionState) -> list[str]:
    state_lines = [
        "🧩 Stan systemu",
        f"Ribbon: {decision_state.ribbon_state.value}",
        f"Momentum H4: {decision_state.momentum_state.value}",
        f"Faza pozycji: {decision_state.position_phase.value}",
        f"Rdzeń: {decision_state.core_action.value}",
        f"Dokładanie: {decision_state.adding_action.value}",
    ]
    if decision_state.position_role is not None:
        state_lines.append(f"Rola: {decision_state.position_role.value.upper()}")
    if decision_state.holding_horizon is not None:
        state_lines.append(
            f"Horyzont: {decision_state.holding_horizon.value.upper()}"
        )
    if decision_state.strategic_review_required:
        state_lines.append("Przegląd strategiczny: WYMAGANY")
    return state_lines


def build_decision_report(
    instrument_id: str,
    current_price: float,
    moving_average_levels: Mapping[int, float],
    position: PositionSnapshot | None,
    latest_confirmed_price: float | None = None,
) -> str:
    confirmed_price = latest_confirmed_price or current_price
    decision_state = build_decision_state(
        current_price=current_price,
        latest_confirmed_price=confirmed_price,
        moving_average_levels=moving_average_levels,
        position=position,
    )
    return "\n".join(
        [f"🧭 Raport decyzyjny — {instrument_id}"]
        + build_system_state_lines(decision_state)
        + build_two_sided_scenario_lines(
            current_price=current_price,
            moving_average_levels=moving_average_levels,
            position=position,
            decision_state=decision_state,
        )
        + build_position_assessment_lines(
            current_price=current_price,
            latest_confirmed_price=confirmed_price,
            position=position,
            decision_state=decision_state,
        )
    )
