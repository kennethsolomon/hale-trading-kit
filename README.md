# Hale Trading Kit

Hale is a risk-first crypto trading agent for Claude Code. You send a chart screenshot and ask for a trade call. Hale reads the structure top-down, offers to research the coin's news and macro calendar first, and returns a fixed-template call (bias, setup, entry, stop, targets, R:R, size, grade) or "NO TRADE" with the exact trigger that would turn it into a trade. It covers spot and USDT perpetuals (Bybit as the default example venue, longs and shorts), defaults to paper mode, sizes every trade from the stop, and holds its risk rules under pushback. Live trading unlocks only after the paper gate, and perps carry extra guardrails (isolated margin, leverage cap, liquidation check, fees and funding inside the risk budget).

## What Hale is NOT

- Not financial advice. Calls are educational analysis.
- No guarantees. Any single trade can lose, and trading crypto, especially with leverage, can lose all capital.
- Not an income plan. Most retail traders lose money: the BIS found that a majority of retail crypto app users in nearly every economy likely lost money on their bitcoin ([BIS Bulletin 69, Feb 2023](https://www.bis.org/publ/bisbull69.htm)).
- Not a data feed. Hale only sees what is in your screenshot and what you send. It asks for funding, open interest, and higher-timeframe charts instead of inventing them.

## Quick start

1. Copy `.claude/agents/hale.md` into the `.claude/agents/` folder of your project (or keep this repo as your project).
2. Open the project in Claude Code.
3. Send one or more chart screenshots and type: `Hale, trade call?`
4. Answer Hale's questions (at most 3) and say yes or no to the research offer.
5. Log the result in `journal/paper-trade-journal.md` and `journal/trades.csv`.

## How a call works

1. **Research ask.** If a coin is named, Hale asks once: "Want me to research [COIN] first (news, catalysts, sentiment, macro)?" No means chart-only. Yes means a sourced, dated brief covering the last 7-14 days. A yes applies to that call only.
2. **Top-down read.** Higher timeframe bias, structure, key levels and liquidity, then a match against a fixed playbook (sweep + reclaim, range deviation, breakout-retest, trend pullback, failed breakdown). No match means NO TRADE.
3. **Fixed template.** Invalidation first, then entry, targets, R:R, and size derived from the stop. Grade C, or R:R below 2, is NO TRADE.

Abbreviated sample output (illustrative format only, not a real call):

```
VERDICT: TRADE (conditional)        MODE: PAPER
ASSET / TF: BTCUSDT Perp / 4H
BIAS: Bullish (Daily HH/HL intact)
SETUP: Sweep + reclaim of range low     GRADE: B
INVALIDATION / STOP: <level>, idea wrong if 4H closes below range low
ENTRY: <zone> (limit) | trigger: 15m close back above <level>
TARGETS: TP1 <level> | TP2 <level>
R:R: TP1 <x>R | TP2 <x>R
SIZE (paper 100,000, 1% risk = 1,000): qty = 1,000 / |entry - stop|
FILTERS: BTC n/a | Funding/OI: unknown, please send | News: see research brief
WHAT I CAN'T SEE: Daily chart, funding, OI
CONFIDENCE: Medium. Any single trade can lose.
Educational analysis, not financial advice. Trading crypto, especially with leverage, can lose all capital.
```

A perps call swaps the SIZE line for the perps version and adds an ORDERS line (illustrative format only):

```
SIZE (perps): risk 1,000 (1%, fees incl.) | stop distance <x>% | notional = risk / (stop % + 0.11% fees) | effective leverage <x>x (cap 3x) | margin isolated @ <x>x | liq <price> vs stop <price> (needs >= 2x stop distance past stop) | fees + funding inside the 1%
ORDERS (perps): isolated margin | stop-market placed at entry | TP1/TP2 reduce-only | no adds, no averaging down
```

For NO TRADE, the call gives a REASON and a WOULD BECOME A TRADE IF trigger instead of entry, targets, and size.

## Risk rules

| Rule | Limit |
|---|---|
| Default mode | PAPER on every call |
| Risk per trade | 1% of equity (paper account, or confirmed live risk capital) |
| Daily stop | 2% loss or 2 consecutive losses, then done for the day |
| Weekly stop | 5% loss, then stop until next week and review the journal |
| Peak drawdown | 10% halts live trading and returns to paper |
| Leverage cap | 3x effective, isolated margin, stop order on the exchange |
| Open risk | 2-3% total; correlated same-direction positions count as one bucket |
| Paper-first gate | At least 50 logged paper trades, positive expectancy, 90% or more rule adherence |
| Live sizing | Only after the paper gate, an amount of dedicated risk capital stated in the current conversation, and "live" said on that specific call |
| Perps margin | Isolated only, never cross |
| Perps leverage cap | 3x effective (notional / risk capital); exchange leverage is just a margin tool |
| Perps liquidation check | Liquidation at least 2x the stop distance past the stop, or reduce leverage; if it still fails, NO TRADE |
| Perps fees and funding | Taker ~0.055% per side and funding (every 8h if held) count inside the 1% risk |
| Perps orders | Stop-market on the exchange at entry; take-profits reduce-only; no averaging down, widening stops, or adding to losers; shorts allowed |
| Live venue | Spot on licensed platforms; perps on Bybit USDT perpetuals (check registration in your jurisdiction; in the Philippines Bybit was flagged unregistered by the SEC in Aug 2025) |
| No stable income or small savings | Paper-only |

The full wording is in `.claude/agents/hale.md`. Hale refuses to size above these limits even if asked.

## Journaling workflow

1. After each call, copy the entry block from `journal/paper-trade-journal.md` and fill it in.
2. Append the same fields as one row in `journal/trades.csv`.
3. When the trade closes, record the result in R (not currency) and a mistake tag.
4. Update the running stats table: win rate, average R, expectancy, and the count toward the 50-trade paper requirement.
5. Ask Hale to "review my trades" for a summary by setup, session, and mistake tag. Judge a setup only after 30-50 trades.

## Repo structure

```
hale-trading-kit/
  README.md
  .claude/agents/hale.md          agent definition (copy into your project)
  docs/persona.md                 who Hale is and how Hale works
  docs/research-brief.md          operating brief: competencies, sizing math, psychology, regional notes
  journal/paper-trade-journal.md  journal template and running stats
  journal/trades.csv              trade log (header row only)
  .gitignore
```

## Region note

Hale's regulatory and tax notes default to the Philippines (BSP-registered spot venues, SEC advisories on offshore exchanges). Rules change, so Hale verifies by search before relying on them. If you are elsewhere, tell Hale your jurisdiction and edit the "Philippines context" section of `.claude/agents/hale.md`.

## Disclaimer

This kit is for education and paper practice only. Nothing here is financial, investment, legal, or tax advice. Crypto assets are volatile, leverage can wipe out your entire balance, and past or paper results do not predict future results. Never trade money you need for rent, food, bills, or debt, and never borrow to trade. Never share your seed phrase or a withdrawal-enabled API key with anyone, including an AI agent. You are solely responsible for your decisions. If trading is causing you distress, stop and talk to someone you trust or a professional.
