"""Generate a synthetic billing warehouse for a fictional legal-services
marketplace: clients, jobs (one per document served) and billed line items,
over six monthly billing periods.

The mess is realistic and deliberate:
- a few duplicate line items (the same line loaded twice)
- a few line amounts that do not equal units x rate
- some jobs with no client matter number
- in 2026-08, three line items whose job record had not synced to the jobs
  table yet (an orphan join problem: the classic silent drop)
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 11
OUT = Path("data/warehouse")
PERIODS = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
CLIENTS = [("HWL", "Hartwell & Lowe LLP", 38), ("BRC", "Bramwell Cardenas", 30), ("NGI", "Northgate Insurance Legal", 26)]
JURIS = ["ON", "QC", "BC", "AB", "NY", "CA", "TX"]
CASES = ["Ramsay v. Delorme", "In re Halcyon Holdings", "Patel v. Northline Freight", "Ostrowski v. City Transit",
         "Moreau Estate", "Kingsley v. Arbor Health", "Vance Logistics v. Corrigan", "Lindqvist v. Petra Mining"]
FEES = {"SERVICE_FEE": (1, 85.0), "RUSH_FEE": (1, 60.0), "SAME_DAY_FEE": (1, 120.0),
        "ATTEMPT_FEE": (None, 25.0), "MILEAGE": (None, 0.68), "COURT_FEE": (1, 42.5)}


def month_days(period):
    y, m = map(int, period.split("-"))
    start = date(y, m, 1)
    end = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    return start, end


def main():
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    clients = [{"client_id": c, "client_name": n} for c, n, _ in CLIENTS]
    jobs, lines = [], []
    job_n, line_n = 400000, 9000000
    matters = {c: [f"{c}-M{rng.randint(10000, 99999)}" for _ in range(10)] for c, _, _ in CLIENTS}
    for period in PERIODS:
        start, end = month_days(period)
        for cid, _, volume in CLIENTS:
            for _ in range(volume + rng.randint(-5, 6)):
                job_n += 1
                done = start + timedelta(days=rng.randint(0, (end - start).days))
                svc = rng.choices(["STANDARD", "RUSH", "SAME_DAY"], [70, 22, 8])[0]
                status = rng.choices(["SERVED", "NON_SERVE"], [86, 14])[0]
                attempts = 1 if status == "SERVED" and rng.random() < 0.6 else rng.randint(2, 4)
                matter = "" if rng.random() < 0.015 else rng.choice(matters[cid])
                job = {"job_id": f"J{job_n}", "client_id": cid, "matter_id": matter, "case_name": rng.choice(CASES),
                       "jurisdiction": rng.choice(JURIS), "service_type": svc, "status": status,
                       "attempts": attempts, "completed_date": done.isoformat(), "server_id": f"S{rng.randint(100, 160)}"}
                items = [("SERVICE_FEE", 1, FEES["SERVICE_FEE"][1])]
                if svc == "RUSH":
                    items.append(("RUSH_FEE", 1, FEES["RUSH_FEE"][1]))
                if svc == "SAME_DAY":
                    items.append(("SAME_DAY_FEE", 1, FEES["SAME_DAY_FEE"][1]))
                if attempts > 1:
                    items.append(("ATTEMPT_FEE", attempts - 1, FEES["ATTEMPT_FEE"][1]))
                items.append(("MILEAGE", rng.randint(4, 90), FEES["MILEAGE"][1]))
                if rng.random() < 0.3:
                    items.append(("COURT_FEE", 1, FEES["COURT_FEE"][1]))
                for item, units, rate in items:
                    line_n += 1
                    amount = round(units * rate, 2)
                    if rng.random() < 0.012:
                        amount = round(amount + rng.choice([0.01, 1.0, -0.5]), 2)   # bad arithmetic upstream
                    line = {"line_id": f"L{line_n}", "job_id": job["job_id"], "client_id": cid,
                            "billed_period": period, "item_type": item, "units": units, "unit_rate": rate,
                            "amount": amount, "line_date": done.isoformat()}
                    lines.append(line)
                    if rng.random() < 0.008:
                        lines.append(dict(line))                                     # loaded twice
                jobs.append(job)

    # 2026-08: three jobs whose lines were billed before the job record synced.
    orphan_jobs = [j for j in jobs if j["client_id"] == "BRC" and j["completed_date"].startswith("2026-08")][:3]
    jobs = [j for j in jobs if j not in orphan_jobs]

    for name, rows in [("clients", clients), ("jobs", jobs), ("line_items", lines)]:
        with open(OUT / f"{name}.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"{len(jobs)} jobs, {len(lines)} line items, {len(orphan_jobs)} jobs missing from the jobs table")


if __name__ == "__main__":
    main()
