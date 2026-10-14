# What the backtests showed

Every rule the bot shows was tested on history first; this page keeps the results and
their caveats. Prices: Yahoo daily data adjusted for splits and dividends. Costs: the
broker's "Smart" tariff for US shares — 2 per order + 0.02 per share, whole shares only.
Past results do not predict future ones, and none of this is investment advice.

> **RU:** Все правила бота сначала проверены на истории; здесь результаты и оговорки.
> Прошлые результаты не гарантируют будущих; это не инвестиционный совет.

## 1. Can a small account beat "buy and hold"? (2007–2026)

Decisions at a close, trades at the next day's close, slippage 0.05 %. Yearly return
(deepest fall):

| Strategy | 100 € | 1000 € | 10 000 € | 1000 €, no fees |
|---|---|---|---|---|
| Buy and hold S&P 500 | 9.9 % (−46 %) | 10.8 % (−53 %) | 11.0 % (−55 %) | 10.8 % |
| S&P 500 above its 200-day average, monthly | 0.1 % | 8.0 % (−26 %) | 8.6 % (−27 %) | 8.5 % |
| Same, weekly | −1.8 % | 6.8 % | 8.0 % | 8.0 % |
| 12-month momentum rotation, monthly | −0.8 % | 10.6 % (−31 %) | 11.6 % (−34 %) | 10.7 % |

- No strategy beat buy-and-hold on return at any account size, even without fees. Timing
  rules cut the deepest fall roughly in half and cost return.
- Weekly is worse than monthly everywhere: more false signals, more fees.
- Below ~1000 € the per-order fee and whole shares eat any active strategy.

**Consequence:** the project became an analytics bot. Rules turn into hints in a report;
a human decides.

## 2. Freedom24 investment ideas (2020–2026)

All 1185 published stock ideas, 1166 analysed (98 %; prices from the broker, including
delisted stocks, so no survivorship bias). Result at the end of each idea's term against
the S&P 500 over the same dates:

| | Ideas | Mean | Median | S&P 500, same dates | Beat S&P | Target hit | Lost money |
|---|---|---|---|---|---|---|---|
| Closed | 866 | +8.9 % | +2.2 % | +15.8 % | 37 % | 34 % | 47 % |
| Open | 300 | +5.7 % | +0.2 % | +9.3 % | 35 % | 21 % | 49 % |

- An average idea trails the index by ~7 points over its term (10.5 months on average),
  in every year. Results rest on rare rockets with frequent failures.
- Ideas on stocks in a downtrend trailed by −8.4 points, in an uptrend by −3.1.
- Selling at the target is worse still (+4.7 %): the target cuts the rare big winners.

**In the bot:** new ideas appear with this track record next to them — a reason to study
a company, not a signal.

## 3. "Sell if it doesn't grow" — exit rules

Tested on the 866 closed ideas (mean result over the idea's term):

| Rule | Sell → cash | Sell → S&P 500 | Fired | Sale was right |
|---|---|---|---|---|
| Hold to the end | +8.9 % | — | — | — |
| Below the 200-day average 2 months in a row | +2.9 % | +12.6 % | 85 % | 46 % |
| **Trailing the S&P 500 by >15 % over 12 months** | +3.4 % | **+13.9 %** | 83 % | 48 % |
| Stop-loss −20 % from the buy price | +4.7 % | +9.7 % | 49 % | 45 % |
| Trailing stop −20 % from the high | +1.9 % | +10.9 % | 80 % | 44 % |
| The S&P 500 from the start | — | +15.7 % | — | — |

- Selling into cash is worse than holding under every rule.
- Switching into the index helps; the gain comes from the switch itself. The best rule —
  "12-month lag → index" — beat holding in every year 2021–2025. It protects from
  failures at the cost of part of the big winners.

**In the bot:** a holding card shows the lag and the cost of the switch.

## 4. Buy candidates: momentum + trend (2010–2026)

S&P 500 members (only from the date each joined), ranked by 12-month return without the
last month, close above the 200-day average, top 10, reviewed quarterly. Compared with the
equal-weight basket of the same companies:

| Variant | Review | Top | Per year | Basket | Fees on 4000 € | After fees |
|---|---|---|---|---|---|---|
| Momentum only | monthly | 5 / 10 | +25.8 / +22.6 % | +15.3 % | 2.2 / 4.2 % | +23.5 / +18.5 % |
| **Momentum + trend** | quarterly | 5 / 10 | +23.8 / **+21.7 %** | +15.5 % | 1.3 / 2.4 % | +22.6 / +19.3 % |
| + near the 52-week high | monthly | 10 | +19.4 % | +15.3 % | 5.0 % | +14.4 % |

- **Inflated:** today's member list lacks companies that left the index (some after
  collapses of strong stocks). The basket shares that bias, so the ~6-point edge over it
  is the fairer number, and the real edge is smaller still.
- Quarterly ≈ monthly in return at half the fees. Strong stocks cluster in one sector.

## 5. Crash protection (2007-06 – 2026)

Rule: when the S&P 500 closes a month below its 200-day average, leave stocks for T-bills
(BIL); come back after a month closes above. Filters ("2 months in a row", "3 % / 5 %
below") did worse than the plain rule.

| | Hold the S&P 500 | With the rule |
|---|---|---|
| Deepest fall | −55 % | −26 % |
| Per year | +10.8 % | +9.1 % |

14 signals: **1 helped** (2008), 11 false alarms (the market rose ~6 % on average while out),
the rest even. Insurance against a rare long crash, paid for by frequent false alarms.

**In the bot:** 🟢/🟡/🔴 status in every report, the table of all signals on the Market
page, and a daily check that alerts at once when the month-end status changes. The
numbers are recomputed for every report.
