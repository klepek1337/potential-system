# Unrealized profit protection

The engine converts peak-PnL thinking into a worst-case floor. It combines the manually registered
entry, original stop and optional current USD/USDC position value with the current price and
one-way dominant EMA anchor.

| Condition | Cumulative proposed reduction |
|---|---:|
| Below +1R | 0% |
| +1R | 50% |
| +2R | 65% |
| +3R or at least 2.5 ATR from dominant EMA | 80% |

The Telegram report estimates the result if the proposed fraction were realized now and the
remainder later hit the current stop anchor. It is explicitly advisory: the bot never assumes an
order was executed. After acting, update the manual position with `position set`.

Notification stage is persisted in SQLite so the same reduction is not repeated every hour. Fees,
funding and slippage are not included yet. The base-asset amount is estimated as
`position_value_usd / current_price`, because OKX displays the position in dollars. Therefore the
displayed floor is an estimate, not a guarantee.
