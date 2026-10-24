"""Run every client delivery for every billing period in the warehouse.

    python run.py

output/outbox/   files that passed reconciliation and would be sent
output/blocked/  files that failed, kept for diagnosis, never sent
output/delivery_log.csv, output/holds.csv, output/notes/, output/summary.json
"""
import json
import shutil
from pathlib import Path

import pandas as pd

from delivery.notes import facts_for, grounded, per_job_amounts, write_note
from delivery.pipeline import build, connect, load_specs

OUT = Path("output")
PERIODS = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]


def main():
    for d in ("outbox", "blocked", "notes"):
        shutil.rmtree(OUT / d, ignore_errors=True)
        (OUT / d).mkdir(parents=True)
    con = connect(Path("data/warehouse"))
    specs = load_specs(Path("clients"))
    log, holds, excluded = [], [], []
    for period in PERIODS:
        for spec in specs:
            r = build(con, spec, period)
            folder = OUT / ("blocked" if r.status == "BLOCKED" else "outbox") / spec["client_id"]
            folder.mkdir(parents=True, exist_ok=True)
            (folder / r.filename).write_text(r.text)
            note, note_src = write_note(r, spec)
            if note:
                bad = grounded(note, facts_for(r, spec) | per_job_amounts(r))
                assert not bad, f"ungrounded figures in note: {bad}"
                (OUT / "notes" / f"{r.client_id}_{period}.md").write_text(note)
            log.append({"period": period, "client_id": r.client_id, "client": spec["client_name"],
                        "format": spec["format"], "status": r.status, "due": r.due, "file": r.filename,
                        "source_lines": r.source["lines"], "source_amount": r.source["amount"],
                        "delivered_amount": r.delivered["amount"], "delivered_documents": r.delivered["documents"],
                        "held_lines": len(r.held), "held_amount": round(float(r.held["amount"].sum()), 2),
                        "excluded_lines": len(r.excluded), "excluded_amount": round(float(r.excluded["amount"].sum()), 2),
                        "duplicates_removed": r.duplicates_removed, "missing_lines": len(r.missing_line_ids),
                        "missing_line_ids": " ".join(r.missing_line_ids),
                        "checks": " | ".join(f"{'PASS' if ok else 'FAIL'} {name}: {detail}" for name, ok, detail in r.checks),
                        "note": note_src})
            for df, sink in ((r.held, holds), (r.excluded, excluded)):
                if len(df):
                    sink.append(df[["line_id", "job_id", "client_id", "billed_period", "item_type", "amount", "reason"]])
            print(f"{period} {r.client_id:4} {r.status:21} source ${r.source['amount']:>10,.2f}  "
                  f"file ${r.delivered['amount']:>10,.2f}  held {len(r.held):>2}  excluded {len(r.excluded):>2}")

    log = pd.DataFrame(log)
    log.to_csv(OUT / "delivery_log.csv", index=False)
    pd.concat(holds).to_csv(OUT / "holds.csv", index=False)
    pd.concat(excluded).to_csv(OUT / "excluded.csv", index=False)
    blocked = log[log.status == "BLOCKED"]
    summary = {
        "deliveries": int(len(log)), "clients": int(log.client_id.nunique()), "periods": len(PERIODS),
        "delivered_clean": int((log.status == "DELIVERED").sum()),
        "delivered_with_holds": int((log.status == "DELIVERED_WITH_HOLDS").sum()),
        "blocked": int(len(blocked)),
        "source_amount": round(float(log.source_amount.sum()), 2),
        "delivered_amount": round(float(log.delivered_amount.sum()), 2),
        "held_lines": int(log.held_lines.sum()), "held_amount": round(float(log.held_amount.sum()), 2),
        "excluded_amount": round(float(log.excluded_amount.sum()), 2),
        "duplicates_removed": int(log.duplicates_removed.sum()),
        "blocked_detail": blocked[["period", "client", "missing_lines", "source_amount", "delivered_amount",
                                   "held_amount"]].to_dict("records"),
        "unexplained_gap_in_sent_files": 0.0,
    }
    sent = log[log.status != "BLOCKED"]
    summary["unexplained_gap_in_sent_files"] = round(float(
        (sent.source_amount - sent.delivered_amount - sent.held_amount - sent.excluded_amount).abs().sum()), 2)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "blocked_detail"}, indent=2))


if __name__ == "__main__":
    main()
