# IMC Prosperity 4 — Tutorial Round Strategy

> **Best score:** 2,472 PnL on platform  
> **Assets:** EMERALDS + TOMATOES | **Position limit:** 80 each

---

## Repo Structure

```
imc_prosperity_tutorial/
├── solutions/
│   └── v14.py          ← best solution (2,472 PnL)
├── prosperity4bt/      ← backtester based from Jmerle
├── data/               ← round 0 market data (day -1, day -2)
├── datamodel.py        ← required by all solutions
└── README.md
```

---

## How to Run

```bash
# Install dependencies
pip install typer orjson tqdm jsonpickle ipython

# Run backtest (from this folder)
python -m prosperity4bt solutions/v14.py 0 --no-vis

# Single day only
python -m prosperity4bt solutions/v14.py 0-(-1) --no-vis
```

> Local scores are for **relative comparison only**. Platform score is ground truth.  
> Local EMERALDS numbers are inflated by the backtester — ignore them.

---

## The Two Assets

### EMERALDS
Fair value is **always 10,000**. Never moves.  
Bots post walls at 9992/10008 every tick.  
Strategy: take any mispriced order, post 1 tick inside bot walls (9993/10007).

### TOMATOES
Fair value is **dynamic** — estimated each tick via EMA on popular-mid.  
More volatile, more opportunity, needs careful inventory management.

---

## v14 Strategy — TOMATOES

Four layers in priority order:

```
1. EMERGENCY  →  position ≥ 78: flatten immediately
2. TAKE       →  grab anything strictly mispriced vs FV (edge = 0)
3. CLEAR      →  reduce inventory above soft limit (50)
4. MAKE       →  passive quotes with skew + vol scaling
```

**MAKE layer uses three signals:**

| Signal | What it does |
|--------|-------------|
| OBI target inventory | Order book imbalance sets a target position. Bid-heavy → target short. Ask-heavy → target long. Skew quotes toward target, not just toward zero. |
| Nonlinear inventory skew | Gentle price shift at normal positions, aggressive quadratic ramp near limits. |
| Volatility-adjusted sizing | Rolling 10-tick spread. Wide market → trade smaller. Calm market → full size. |

---

## Version History

| Version | Score | Notes |
|---------|-------|-------|
| v11 | 2,380 | Baseline — EMA FV, nonlinear skew, dynamic take edge |
| v13 | 2,423 | + OBI target, vol scaling, mean reversion take edge |
| v12 | 2,437 | Simpler — take edge=0, linear skew, no signals |
| **v14** | **2,472** | Best — take edge=0 + OBI + vol scaling + nonlinear skew |
| v15 | 2,425 | AR(2) FV + OBI conflicted, hurt score |
| v16 | ~2,200 | Spread=4 too tight for our FV quality |

---

## Key Lessons

1. **Tighter EMERALDS quotes saturate position too fast** — wall+1 (9993/10007) is the right posting price, not 9999/10001
2. **Take edge=0 beats dynamic edge** — if it's mispriced vs FV, just take it
3. **AR(2) conflicts with OBI** — they both anticipate direction and fight each other
4. **Spread=5 is correct for our FV quality** — only tighten after improving FV accuracy
5. **One change at a time** — otherwise you can't attribute what moved the score

---

## Concepts Quick Reference

| Term | Plain English |
|------|--------------|
| Market-making | Post buy below FV and sell above FV, earn the spread when both fill |
| Fair value (FV) | Your best estimate of the true price each tick |
| EMA | Smoothed average — weights recent prices more than old ones |
| Popular-mid | Average of highest-volume bid and ask (more stable than best bid/ask) |
| OBI | (bid vol − ask vol) / total vol — tells you who's winning, buyers or sellers |
| Inventory skew | Shift quotes to naturally push position back toward target |
| Vol-adjusted sizing | Trade smaller when market is uncertain, full size when calm |
| Take order | Cross the spread, hit existing order, fills immediately |
| Make order | Post limit order, wait for someone to hit you, earns spread |

---

Reference:
Backtester based from  [Jmerle](https://github.com/jmerle/)
