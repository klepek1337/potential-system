from collections.abc import Mapping

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
) -> list[str]:
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
    target_reached = False
    thesis_level_breached = False
    if position.direction is PositionDirection.LONG:
        stop_breached = (
            position.stop_loss_price is not None
            and current_price <= position.stop_loss_price
        )
        target_reached = (
            position.target_price is not None
            and current_price >= position.target_price
        )
        thesis_level_breached = (
            position.thesis_support_price is not None
            and latest_confirmed_price < position.thesis_support_price
        )
    else:
        stop_breached = (
            position.stop_loss_price is not None
            and current_price >= position.stop_loss_price
        )
        target_reached = (
            position.target_price is not None
            and current_price <= position.target_price
        )
        thesis_level_breached = (
            position.thesis_resistance_price is not None
            and latest_confirmed_price > position.thesis_resistance_price
        )

    if stop_breached:
        verdict = "STOP NARUSZONY — teza pozycji wymaga natychmiastowego przeglądu."
    elif target_reached:
        verdict = "CEL OSIĄGNIĘTY — oceń realizację zysku zgodnie z planem."
    elif thesis_level_breached:
        verdict = "RUCH ZDYSKWALIFIKOWANY — naruszono poziom tezy."
    elif signed_position_result < 0:
        verdict = "TEZA JESZCZE AKTYWNA, ALE NIE DOKŁADAJ DO STRATY."
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


def build_decision_report(
    instrument_id: str,
    current_price: float,
    moving_average_levels: Mapping[int, float],
    position: PositionSnapshot | None,
    latest_confirmed_price: float | None = None,
) -> str:
    confirmed_price = latest_confirmed_price or current_price
    return "\n".join(
        [f"🧭 Raport decyzyjny — {instrument_id}"]
        + build_two_sided_scenario_lines(
            current_price=current_price,
            moving_average_levels=moving_average_levels,
            position=position,
        )
        + build_position_assessment_lines(
            current_price=current_price,
            latest_confirmed_price=confirmed_price,
            position=position,
        )
    )
