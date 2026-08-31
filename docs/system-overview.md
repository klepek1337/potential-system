# Position-risk architecture

The system is layered and read-only:

1. `PositionStore` receives manual entry, stop, direction, current USD value and leverage.
2. Existing H4 SMA alerts continue unchanged.
3. Configured EMA 20/50/120/200 levels are calculated separately.
4. The dominant-EMA engine scans from the smallest timeframe, rejects chop and proposes an
   ATR-buffered anchor.
5. The anchor ratchets only toward profit.
6. Profit protection proposes partial reductions and calculates a worst-case floor.
7. Telegram communicates decisions; no component has authenticated OKX trading access.

Merge the stacked pull requests in order. Their narrow interfaces also allow a later AI market-news
modifier without granting the model authority to place or edit orders.
