"""Offline Monte-Carlo of the upgrade economy (mirrors server.py upgrade rules). Usage: python tests/economy_sim.py"""
import random
import sys

RTP, MAX_CHANCE, MIN_CHANCE, CB, CB_MIN = 0.85, 0.75, 0.01, 1.0, 10.0
RAIN = {"threshold": 4000.0, "lo": 0.20, "hi": 0.30, "single": 0.60, "spins": 600}
PRICES = [5, 10, 20, 35, 50, 80, 120, 200, 350, 500, 800, 1200, 2000, 3500, 5000]


def paid_chance(stake, price, fixed):
    base = min(MAX_CHANCE, stake / price * RTP)
    if not fixed or stake < CB_MIN or price <= CB:
        return base
    return max(0.0, (stake * RTP - CB) / (price - CB))


def run(strategy_mix, players=200, spins=40000, seed=1, rain_on=True, cashback_on=True, fixed=True):
    rng = random.Random(seed)
    bal = [rng.choice([160, 400, 800, 2000]) for _ in range(players)]
    deposited = sum(bal)
    bank = deposited / 0.8
    commission = bank - deposited
    pool = 0.0
    rain = None
    st = {"wagered": 0.0, "prizes": 0.0, "cashback": 0.0, "wins": 0, "forced": 0, "spins": 0, "rain_wins": 0}
    by = {k: [0.0, 0.0] for k in strategy_mix}
    styles = [rng.choice(strategy_mix) for _ in range(players)]
    for _ in range(spins):
        i = rng.randrange(players)
        style = styles[i]
        if bal[i] < 1:
            continue
        if style == "cashback_farm":
            stake = min(bal[i], 10.0)
            price = max(p for p in PRICES if stake / p * RTP >= MIN_CHANCE)
        elif style == "greedy":
            price = rng.choice([p for p in PRICES if p * MAX_CHANCE <= bal[i]] or [None])
            if price is None:
                continue
            stake = round(price * MAX_CHANCE, 2)
        else:
            price = rng.choice(PRICES)
            stake = round(min(bal[i], price * rng.uniform(0.05, MAX_CHANCE)), 2)
        if stake <= 0 or stake / price * RTP < MIN_CHANCE:
            continue
        chance, shown = paid_chance(stake, price, fixed), min(MAX_CHANCE, stake / price)
        bal[i] -= stake
        pool += stake * RTP
        st["wagered"] += stake
        st["spins"] += 1
        by[style][0] += stake
        if rain_on:
            if rain and rain["spins"] <= 0:
                pool += rain["left"]
                rain = None
            if not rain and pool >= RAIN["threshold"]:
                budget = pool * rng.uniform(RAIN["lo"], RAIN["hi"])
                pool -= budget
                rain = {"left": budget, "spins": RAIN["spins"]}
            if rain:
                rain["spins"] -= 1
        luck = bool(rain) and price <= rain["left"] * RAIN["single"]
        win = rng.random() < (shown if luck else chance)
        if win:
            headroom = (bank - commission) - (sum(bal) + 0)
            if headroom < price:
                win = False
                st["forced"] += 1
            elif luck:
                rain["left"] -= price
                st["rain_wins"] += 1
            elif pool >= price:
                pool -= price
            else:
                win = False
                st["forced"] += 1
        if win:
            bal[i] += price
            st["prizes"] += price
            st["wins"] += 1
            by[style][1] += price
        elif cashback_on and stake >= CB_MIN and pool >= CB and not (fixed and luck):
            pool -= CB
            bal[i] += CB
            st["cashback"] += CB
            by[style][1] += CB
    paid = st["prizes"] + st["cashback"]
    held = sum(bal)
    return {
        "spins": st["spins"], "rtp_real": round(paid / st["wagered"], 4), "cashback_share": round(st["cashback"] / st["wagered"], 4),
        "forced_pct_of_wins": round(st["forced"] / max(1, st["wins"] + st["forced"]), 4), "rain_wins": st["rain_wins"],
        "ceiling_ok": paid <= RTP * st["wagered"] + 1e-6, "solvent": bank - commission >= held - 1e-6,
        "site_profit_rap": round((bank - commission) - held, 2), "commission_kept": round(commission, 2),
        "rtp_by_style": {k: round(v[1] / v[0], 3) if v[0] else None for k, v in by.items()},
    }


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    for fixed in (False, True):
        for mix in (["mixed"], ["greedy"], ["cashback_farm"], ["mixed", "greedy", "cashback_farm"]):
            r = run(mix, seed=seed, fixed=fixed, players=500, spins=200000)
            print("FIXED" if fixed else "OLD  ", "+".join(mix), r)
