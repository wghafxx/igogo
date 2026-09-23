"""Per-staff metrics for today / a period / all time. Built only from staff collections, so they survive economy resets."""
from staff_shifts import by_day, utc, worked_seconds


def _in(t, start, end):
    t = utc(t)
    return t is not None and (start is None or t >= start) and (end is None or t < end)


def _latest(reports):
    grouped = {}
    for r in reports:
        g = grouped.setdefault(r["deposit_id"], {"first": r["created_at"], "latest": r, "versions": 0})
        g["versions"] += 1
        if utc(r["created_at"]) < utc(g["first"]):
            g["first"] = r["created_at"]
        if r["version"] > g["latest"]["version"]:
            g["latest"] = r
    return grouped


async def load(db, staff_id):
    reports = await db.staff_reports.find({"staff_id": staff_id, "kind": "intake"}, {"_id": 0, "plan.issued_skins": 0}).to_list(None)
    moves = await db.staff_moves.find({"staff_id": staff_id}, {"_id": 0}).to_list(None)
    shifts = await db.staff_shifts.find({"staff_id": staff_id}, {"_id": 0}).sort("started_at", -1).to_list(5000)
    return reports, moves, shifts


def holdings(reports, moves):
    latest = _latest(reports).values()
    got_n = sum(g["latest"]["items_count"] for g in latest)
    got_v = sum(g["latest"]["total_rap"] for g in latest)
    out = [m for m in moves if m["status"] == "confirmed"]
    return {"items": got_n - sum(m["items_count"] for m in out), "value": round(got_v - sum(m["value_total"] for m in out), 2)}


def compute(reports, moves, shifts, start, end):
    groups = _latest(reports)
    accepted = [g for g in groups.values() if _in(g["first"], start, end)]
    approved = [r for r in reports if r["status"] == "approved" and _in((r.get("decision") or {}).get("at"), start, end)]
    rejected = [r for r in reports if r["status"] == "rejected" and _in((r.get("decision") or {}).get("at"), start, end)]
    current = [g["latest"] for g in groups.values()]
    review = [r for r in current if r["status"] == "submitted"]

    def moved(kind):
        rows = [m for m in moves if m["kind"] == kind and m["status"] == "confirmed" and _in(m.get("decided_at"), start, end)]
        return {"count": len(rows), "items": sum(m["items_count"] for m in rows), "value": round(sum(m["value_total"] for m in rows), 2)}

    return {
        "accepted": {"items": sum(g["latest"]["items_count"] for g in accepted), "value": round(sum(g["latest"]["total_rap"] for g in accepted), 2)},
        "approved": {"count": len(approved), "credited": round(sum(float(r.get("credited") or r["plan"]["credited"]) for r in approved), 2),
                     "value": round(sum(r["total_rap"] for r in approved), 2)},
        "processed": len(accepted),
        "review": {"count": len(review), "value": round(sum(r["total_rap"] for r in review), 2)},
        "revision": sum(1 for r in current if r["status"] == "revision"),
        "rejected": len(rejected),
        "transferred": moved("transfer"),
        "returned": moved("return"),
        "holdings": holdings(reports, moves),
        "worked_seconds": sum(worked_seconds(s, start, end) for s in shifts),
        "flags": {"long_shifts": sum(1 for s in shifts if _in(s["started_at"], start, end) and
                                     ((utc(s.get("ended_at")) or utc(s.get("last_seen")) or utc(s["started_at"])) - utc(s["started_at"])).total_seconds() > 12 * 3600),
                  "gaps_seconds": sum(int(s.get("gaps_seconds", 0)) for s in shifts if _in(s["started_at"], start, end))},
    }


def details(reports, moves, shifts, start, end):
    groups = _latest(reports)
    requests, items = [], []
    for dep_id, g in groups.items():
        if not _in(g["first"], start, end):
            continue
        r = g["latest"]
        requests.append({"deposit_id": dep_id, "report_id": r["id"], "version": r["version"], "versions": g["versions"], "status": r["status"],
                         "player": r["player"], "items_count": r["items_count"], "total_rap": r["total_rap"],
                         "credited": r.get("credited"), "first_submitted_at": g["first"], "decision": r.get("decision")})
        items += [{**i, "deposit_id": dep_id, "status": r["status"]} for i in r["items"]]
    requests.sort(key=lambda x: utc(x["first_submitted_at"]), reverse=True)
    in_moves = [m for m in moves if _in(m.get("decided_at") or m["created_at"], start, end)]
    in_shifts = [s for s in shifts if worked_seconds(s, start, end) or _in(s["started_at"], start, end)]
    return {"requests": requests, "items": items, "moves": sorted(in_moves, key=lambda m: utc(m["created_at"]), reverse=True),
            "shift_ids": [s["id"] for s in in_shifts], "days": by_day(shifts, start, end)}
