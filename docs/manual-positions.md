# Manual position registry

The registry gives the reporting engine position context without OKX credentials. It is
read-only from the market's perspective: commands only update a local JSON file and never place,
edit, or close an order.

```powershell
python -m ma_alert_bot position set SOL-USDT-SWAP long `
  --entry 102.42 --stop 99.50 --value 6025 --leverage 4

python -m ma_alert_bot position list
python -m ma_alert_bot position remove SOL-USDT-SWAP
```

`value` is the current USD/USDC position value displayed by OKX and `leverage` is optional. Entry
and stop are required because downstream risk
reports use them to calculate distance to invalidation and R multiples. A long stop must be below
entry; a short stop must be above entry.

Because the displayed notional changes with mark price, downstream dollar PnL is an estimate. The
default file is `data/positions.json`. Change it with `POSITIONS_FILE_PATH`. Do not edit it
while another position command is running; writes are atomic to avoid a partially written file.
