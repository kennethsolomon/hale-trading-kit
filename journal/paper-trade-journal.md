# Paper Trade Journal

Log every call, taken or skipped-by-rule, in R-multiples. Copy the entry block below for each trade and append the same fields as one row in `trades.csv`. Judge process separately from outcome. A setup needs about 30-50 trades before you judge it, and the paper-to-live gate needs at least 50 logged trades.

## Running stats

Update after every closed trade. Formulas use R-multiples only.

| Metric | Value | How to compute |
|---|---|---|
| Trades logged | 0 | count of rows in `trades.csv` |
| Progress to 50-trade paper requirement | 0 / 50 | trades logged out of 50 |
| Wins / losses / breakeven | 0 / 0 / 0 | count by sign of result_r |
| Win rate | n/a | wins / trades |
| Average win (R) | n/a | mean of winning result_r |
| Average loss (R) | n/a | mean of losing result_r (absolute value) |
| Expectancy (R per trade) | n/a | (win rate x avg win) - (loss rate x avg loss) |
| Profit factor | n/a | gross winning R / gross losing R |
| Rule adherence | n/a | trades with no mistake tag / trades logged (gate: 90% or more) |

Paper-to-live gate: at least 50 logged trades, positive expectancy, rule adherence of 90% or more. Passing the gate does not lift the live caps (1% risk per trade, 2% daily and 5% weekly stops, 3x effective leverage cap, isolated margin on perps, venue checked for your jurisdiction).

## Entry template

Copy this block per trade.

```
### YYYY-MM-DD HH:MM PHT | <PAIR> | <TF>
- Date (PHT):
- Pair:
- Timeframe:
- Side (long/short):
- Market (spot/perps):
- Leverage (effective x / exchange x):
- Liquidation price (perps):
- Setup (playbook name):
- Grade (A/B/C):
- Entry:
- Stop:
- Targets (TP1 / TP2):
- Size (qty and notional):
- Fees + funding (total, in currency and R):
- Mode (paper/live):
- Research done (yes/no):
- Result (R):
- Notes:
- Mistake tag (none / moved-stop / early-entry / fomo / revenge / oversize / skipped-stop / other):
```

## Mistake tags

| Tag | Meaning |
|---|---|
| none | followed the plan |
| moved-stop | widened or removed the stop |
| early-entry | entered before the trigger |
| fomo | chased price away from a level |
| revenge | re-entered fast after a loss |
| oversize | risked more than the cap |
| skipped-stop | no exchange stop order |
| other | explain in notes |

## Entries

(none yet)
