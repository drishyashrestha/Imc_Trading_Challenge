"""
IMC Prosperity 4 — Tutorial Round | v14
=========================================
Platform score: 2,472  (best so far)
Previous bests: v13=2,423 | 50497 =2,437 | 50546 (base)=2,380

═══════════════════════════════════════════════
EMERALDS  (~1,000 PnL)
═══════════════════════════════════════════════
FV is fixed forever at 10,000. Never changes.

  TAKE:  buy any ask strictly below 10,000
         sell any bid strictly above 10,000
         (rare arb — free money when it appears)

  MAKE:  find the highest bot wall bid below FV
         and lowest bot wall ask above FV.
         Post 1 tick inside those walls (wall_bid+1 / wall_ask-1).
         This gives us queue priority over bots without quoting too tight.
         Posting at 9993/10007 is intentional — quoting tighter (e.g. 9999/10001)
         saturates our 80-unit limit too fast and kills PnL.

  No inventory skew needed — EMERALDS fills are predictable and symmetric.

═══════════════════════════════════════════════
TOMATOES  (~1,470 PnL)
═══════════════════════════════════════════════
FV is dynamic — we estimate it each tick via EMA on popular-mid.

  popular-mid = average of (highest-volume bid, highest-volume ask)
  This anchors to where the market has the most depth, not just best price.
  EMA alpha=0.7 means we weight current tick 70% and history 30% — fairly responsive.

  ── LAYER 1: EMERGENCY ──────────────────────
  If position hits ±78 (near the 80 limit), stop everything and flatten.
  Sell into any bid (long emergency) or buy any ask (short emergency).
  Capped to avoid overshooting through zero.

  ── LAYER 2: TAKE ───────────────────────────
  Take edge = 0 always.
  Buy any ask strictly below FV, sell any bid strictly above FV.
  No minimum edge required — grab everything mispriced.
  Simpler than dynamic edge and scores better (learned from 50497 comparison).

  ── LAYER 3: CLEAR ──────────────────────────
  When position > SOFT (50): sell into bids at or above FV to reduce inventory.
  When position < -SOFT: buy from asks at or below FV.
  HARD tier (70+): accept 1 tick worse price to offload faster.
  Goal: keep inventory in the healthy -50 to +50 range.

  ── LAYER 4: MAKE ───────────────────────────
  Passive quotes on both sides with three adjustments:

  [A] OBI target inventory
      Order book imbalance = (total bid vol - total ask vol) / total vol
      Smoothed with EMA alpha=0.3 (slower — avoids single-tick noise).
      Bid-heavy book (OBI>0) → price likely falls → we want to be short → target=-30
      Ask-heavy book (OBI<0) → price likely rises → we want to be long → target=+30
      Inventory skew is now based on deviation from this target, not from zero.
      This means we don't fight the market's direction.

  [B] Nonlinear inventory skew on price
      Below soft limit: linear shift of 2.5 ticks per unit of skew.
      Above soft limit: quadratic ramp adds up to 4.0 extra ticks.
      Gives gentle pressure at normal positions, strong exit pressure at extremes.

  [C] Volatility-adjusted sizing
      Track rolling 10-tick average of best_ask - best_bid (market spread).
      Reference spread = 14 (normal TOMATOES market).
      When spread is wide (volatile): scale position size DOWN — avoid getting
      filled aggressively on both sides during noisy/uncertain periods.
      When spread is tight (calm): trade full size.
      vol_scalar = clamp(ref_spread / avg_spread, 0.4, 1.0)

═══════════════════════════════════════════════
CONSTANTS
═══════════════════════════════════════════════
LIMIT=80       position limit (both assets)
TOM_SPREAD=5   half-spread for passive MAKE quotes
TOM_SOFT=50    start clearing / skewing sizing
TOM_HARD=70    accept worse price to clear faster
TOM_EMERG=78   emergency flatten — drop everything
TOM_OBI_ALPHA=0.3   OBI smoothing (slower EMA)
TOM_OBI_SCALE=30    max target inventory from OBI signal
TOM_REF_SPREAD=14   reference market spread for vol scalar
"""

from __future__ import annotations
import json
import math
from datamodel import Order, OrderDepth, TradingState

LIMIT = 80
EM_FV = 10_000

TOM_EMA_ALPHA  = 0.7
TOM_SPREAD     = 5
TOM_INV_SKEW   = 2.5
TOM_SOFT       = 50
TOM_HARD       = 70
TOM_EMERG      = 78

TOM_OBI_ALPHA  = 0.3
TOM_OBI_SCALE  = 30
TOM_REF_SPREAD = 14


def _take_orders(product: str, od: OrderDepth, fv: float, rb: int, rs: int, pos: int):
    orders = []
    for ask in sorted(od.sell_orders):
        if ask >= fv or rb <= 0:
            break
        q = min(-od.sell_orders[ask], rb)
        orders.append(Order(product, ask, q))
        rb -= q
        pos += q

    rs = LIMIT + pos
    for bid in sorted(od.buy_orders, reverse=True):
        if bid <= fv or rs <= 0:
            break
        q = min(od.buy_orders[bid], rs)
        orders.append(Order(product, bid, -q))
        rs -= q
        pos -= q

    return orders, LIMIT - pos, LIMIT + pos, pos


class Trader:

    def run(self, state: TradingState):
        sv = json.loads(state.traderData) if state.traderData else {}
        result = {}

        for product, od in state.order_depths.items():
            if not od.buy_orders or not od.sell_orders:
                result[product] = []
                continue
            pos = state.position.get(product, 0)
            if product == "EMERALDS":
                result[product] = self._emeralds(od, pos)
            elif product == "TOMATOES":
                result[product] = self._tomatoes(od, pos, sv)
            else:
                result[product] = []

        return result, 0, json.dumps(sv)

    # ── EMERALDS: unchanged ───────────────────────────────────────────────
    def _emeralds(self, od: OrderDepth, pos: int):
        orders, rb, rs, pos = _take_orders("EMERALDS", od, EM_FV, LIMIT - pos, LIMIT + pos, pos)

        bids_below = [p for p in od.buy_orders if p < EM_FV]
        asks_above = [p for p in od.sell_orders if p > EM_FV]
        wall_bid = max(bids_below) if bids_below else EM_FV - 8
        wall_ask = min(asks_above) if asks_above else EM_FV + 8

        bid_px = min(wall_bid + 1, EM_FV - 1)
        ask_px = max(wall_ask - 1, EM_FV + 1)

        if rb > 0:
            orders.append(Order("EMERALDS", bid_px, rb))
        if rs > 0:
            orders.append(Order("EMERALDS", ask_px, -rs))

        return orders

    # ── TOMATOES: v14 ────────────────────────────────────────────────────
    def _tomatoes(self, od: OrderDepth, pos: int, sv: dict):
        orders = []
        rb = LIMIT - pos
        rs = LIMIT + pos

        # Fair value: EMA on popular-mid
        pop_bid = max(od.buy_orders, key=lambda p: od.buy_orders[p])
        pop_ask = max(od.sell_orders, key=lambda p: -od.sell_orders[p])
        pop_mid = (pop_bid + pop_ask) / 2.0
        fv = TOM_EMA_ALPHA * pop_mid + (1.0 - TOM_EMA_ALPHA) * sv.get("fv", pop_mid)
        sv["fv"] = fv

        ff = math.floor(fv)
        fc = math.ceil(fv)

        bb = max(od.buy_orders)
        ba = min(od.sell_orders)

        # OBI → smoothed target inventory
        total_bid = sum(od.buy_orders.values())
        total_ask = sum(-v for v in od.sell_orders.values())
        denom = total_bid + total_ask
        raw_obi = (total_bid - total_ask) / denom if denom else 0.0
        obi = TOM_OBI_ALPHA * raw_obi + (1.0 - TOM_OBI_ALPHA) * sv.get("obi", 0.0)
        sv["obi"] = obi
        # bid-heavy (obi>0) → price likely falls → target short
        target_inv = -round(obi * TOM_OBI_SCALE)
        target_inv = max(-TOM_SOFT, min(TOM_SOFT, target_inv))

        # Volatility scalar from rolling spread
        curr_spread = ba - bb
        sp_hist = sv.get("sp", [])
        sp_hist.append(curr_spread)
        if len(sp_hist) > 10:
            sp_hist = sp_hist[-10:]
        sv["sp"] = sp_hist
        avg_spread = sum(sp_hist) / len(sp_hist)
        vol_scalar = max(0.4, min(1.0, TOM_REF_SPREAD / max(avg_spread, 1)))

        # Emergency flatten
        if pos >= TOM_EMERG:
            for bid in sorted(od.buy_orders, reverse=True):
                sell_cap = min(rs, pos)
                if sell_cap <= 0:
                    break
                q = min(od.buy_orders[bid], sell_cap)
                orders.append(Order("TOMATOES", bid, -q))
                rs -= q
                pos -= q
            return orders

        if pos <= -TOM_EMERG:
            for ask in sorted(od.sell_orders):
                buy_cap = min(rb, -pos)
                if buy_cap <= 0:
                    break
                q = min(-od.sell_orders[ask], buy_cap)
                orders.append(Order("TOMATOES", ask, q))
                rb -= q
                pos += q
            return orders

        # TAKE: edge=0 always (take everything strictly mispriced vs FV)
        take_orders, rb, rs, pos = _take_orders("TOMATOES", od, fv, rb, rs, pos)
        orders.extend(take_orders)

        # CLEAR near soft limit
        if pos > TOM_SOFT and rs > 0:
            cl = ff - 1 if pos >= TOM_HARD else ff
            for bid in sorted(od.buy_orders, reverse=True):
                if bid < cl or rs <= 0 or pos <= TOM_SOFT:
                    break
                q = min(od.buy_orders[bid], rs, pos - TOM_SOFT)
                orders.append(Order("TOMATOES", bid, -q))
                rs -= q
                pos -= q
            rb = LIMIT - pos

        if pos < -TOM_SOFT and rb > 0:
            cl = fc + 1 if -pos >= TOM_HARD else fc
            for ask in sorted(od.sell_orders):
                if ask > cl or rb <= 0 or pos >= -TOM_SOFT:
                    break
                q = min(-od.sell_orders[ask], rb, -pos - TOM_SOFT)
                orders.append(Order("TOMATOES", ask, q))
                rb -= q
                pos += q
            rs = LIMIT + pos

        # MAKE: nonlinear skew based on deviation from OBI target
        inv_dev = pos - target_inv
        skew = inv_dev / LIMIT
        abs_dev = abs(inv_dev)

        if abs_dev > TOM_SOFT:
            excess = (abs_dev - TOM_SOFT) / (LIMIT - TOM_SOFT)
            inv_adj = -skew * (TOM_INV_SKEW + 4.0 * excess * excess)
        else:
            inv_adj = -skew * TOM_INV_SKEW

        bid_px = math.floor(fv - TOM_SPREAD + inv_adj)
        ask_px = math.ceil(fv + TOM_SPREAD + inv_adj)
        bid_px = min(bid_px, ff - 1)
        ask_px = max(ask_px, fc + 1)

        # Sizing: vol-adjusted + target-aware
        if inv_dev > TOM_SOFT:
            bq = max(1, min(rb, int(3 * vol_scalar)))
            sq = max(1, int(rs * vol_scalar))
        elif inv_dev < -TOM_SOFT:
            bq = max(1, int(rb * vol_scalar))
            sq = max(1, min(rs, int(3 * vol_scalar)))
        else:
            dev_skew = inv_dev / LIMIT
            bq = max(1, min(rb, int(rb * (1.0 - max(0.0, dev_skew) * 0.6) * vol_scalar)))
            sq = max(1, min(rs, int(rs * (1.0 + min(0.0, dev_skew) * 0.6) * vol_scalar)))

        if pos < TOM_HARD and bq > 0:
            orders.append(Order("TOMATOES", bid_px, bq))
        if pos > -TOM_HARD and sq > 0:
            orders.append(Order("TOMATOES", ask_px, -sq))

        return orders
