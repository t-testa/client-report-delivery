"""Build output/dashboard.html: delivery status by client and period, the
reconciliation behind every file, the blocked delivery and why, holds, and a
preview of each client's format."""
import html
import json
import re
from pathlib import Path

import pandas as pd

OUT = Path("output")
STATUS = {"DELIVERED": ("good", "✓", "Delivered"), "DELIVERED_WITH_HOLDS": ("warning", "◆", "Delivered, holds"),
          "BLOCKED": ("critical", "✕", "Blocked")}


def esc(v):
    return html.escape(str(v))


def money(v):
    return f"${v:,.2f}"


def chip(s):
    tone, icon, text = STATUS[s]
    return f'<span class="chip {tone}"><span aria-hidden="true">{icon}</span> {text}</span>'


def md(text):
    out, in_list = [], False
    for line in text.splitlines():
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(line))
        if line.startswith("- "):
            out.append(("<ul>" if not in_list else "") + f"<li>{line[2:]}</li>")
            in_list = True
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.strip():
            out.append(f"<p>{line}</p>")
    return "".join(out) + ("</ul>" if in_list else "")


def main():
    log = pd.read_csv(OUT / "delivery_log.csv")
    s = json.loads((OUT / "summary.json").read_text())
    holds = pd.read_csv(OUT / "holds.csv")
    periods = sorted(log.period.unique())
    clients = log.drop_duplicates("client_id")[["client_id", "client", "format"]].values.tolist()
    fmt_name = {"ledes1998b": "LEDES 1998B e-billing", "csv_per_job": "CSV case-management import",
                "json_invoice": "JSON accounting payload"}

    sent = s["deliveries"] - s["blocked"]
    tiles = [("Deliveries run", str(s["deliveries"]), f"{s['clients']} clients × {s['periods']} periods"),
             ("Sent", str(sent), f"{s['delivered_clean']} clean · {s['delivered_with_holds']} with holds"),
             ("Unexplained gap in sent files", money(s["unexplained_gap_in_sent_files"]), "every dollar accounted for"),
             ("Blocked before sending", str(s["blocked"]), "silent join drop caught"),
             ("Held for a fix", money(s["held_amount"]), f"{s['held_lines']} lines, each with a reason"),
             ("Duplicate loads removed", str(s["duplicates_removed"]), "before totals")]
    tiles_html = "".join(f'<div class="tile"><div class="tl">{a}</div><div class="tv">{b}</div><div class="ts">{c}</div></div>'
                         for a, b, c in tiles)

    head = "".join(f"<th>{p}</th>" for p in periods)
    rows = ""
    for cid, name, fmt in clients:
        cells = ""
        for p in periods:
            r = log[(log.client_id == cid) & (log.period == p)].iloc[0]
            tip = (f"{name} {p}\nsource {money(r.source_amount)} ({r.source_lines} lines)\nfile {money(r.delivered_amount)}\n"
                   f"held {money(r.held_amount)} ({r.held_lines})\nexcluded {money(r.excluded_amount)} ({r.excluded_lines})\n"
                   + r.checks.replace(" | ", "\n"))
            cells += f'<td title="{esc(tip)}">{chip(r.status)}<div class="ts">{money(r.delivered_amount)}</div></td>'
        rows += f"<tr><th class='rowh'>{esc(name)}<div class='ts'>{fmt_name[fmt]}</div></th>{cells}</tr>"

    recon = ""
    for r in log.sort_values(["period", "client_id"], ascending=[False, True]).itertuples():
        gap = round(r.source_amount - r.delivered_amount - r.held_amount - r.excluded_amount, 2) + 0.0
        recon += (f"<tr><td>{r.period}</td><td>{esc(r.client)}</td><td>{chip(r.status)}</td><td>{money(r.source_amount)}</td>"
                  f"<td>{money(r.delivered_amount)}</td><td>{money(r.held_amount)}</td><td>{money(r.excluded_amount)}</td>"
                  f"<td class='{'bad' if abs(gap) > 0.005 else ''}'>{money(gap)}</td><td>{r.due}</td></tr>")

    blocked = log[log.status == "BLOCKED"]
    blocked_html = "".join(md((OUT / "notes" / f"{b.client_id}_{b.period}.md").read_text()) for b in blocked.itertuples())

    hold_rows = "".join(f"<tr><td>{h.billed_period}</td><td>{h.client_id}</td><td class='mono'>{h.line_id}</td>"
                        f"<td class='mono'>{h.job_id}</td><td>{h.item_type.replace('_', ' ').lower()}</td>"
                        f"<td>{money(h.amount)}</td><td>{esc(h.reason)}</td></tr>"
                        for h in holds.sort_values(["billed_period", "client_id"], ascending=[False, True]).head(14).itertuples())

    previews = ""
    for cid, name, fmt in clients:
        f = next((OUT / "outbox" / cid).glob(f"{cid}_{periods[-1]}.*"))
        text = "\n".join(f.read_text().splitlines()[:6])
        previews += f'<div class="card"><h3>{esc(name)}</h3><p class="muted">{fmt_name[fmt]} · {f.name}</p><pre>{esc(text)}</pre></div>'

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Client Report Delivery</title><style>
:root{{--bg:#f6f5f2;--surface:#fcfcfb;--line:#e4e2dc;--text:#0b0b0b;--text2:#52514e;--muted:#77756f;--good:#0a8a0a;--warning:#a86f00;--critical:#d03b3b;--code:#f0efec}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#121211;--surface:#1a1a19;--line:#2e2e2b;--text:#f0efec;--text2:#c3c2b7;--muted:#9b998f;--good:#2fbf2f;--warning:#fab219;--critical:#e66767;--code:#232321}}}}
:root[data-theme="dark"]{{--bg:#121211;--surface:#1a1a19;--line:#2e2e2b;--text:#f0efec;--text2:#c3c2b7;--muted:#9b998f;--good:#2fbf2f;--warning:#fab219;--critical:#e66767;--code:#232321}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:24px 16px 48px}}h1{{font-size:22px;margin:0}}h2{{font-size:16px;margin:28px 0 10px}}h3{{font-size:14px;margin:0 0 2px}}
.sub{{color:var(--text2);margin:4px 0 16px}}.muted,.ts{{color:var(--muted);font-size:12px}}.mono{{font-family:ui-monospace,Menlo,monospace;font-size:12px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(170px,100%),1fr));gap:10px}}.tile,.card{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;min-width:0}}
.tl{{color:var(--text2);font-size:12px}}.tv{{font-size:24px;font-weight:650;margin:2px 0}}
.grid3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(330px,100%),1fr));gap:10px}}
.chip{{display:inline-block;font-size:12px;font-weight:600;padding:1px 8px;border-radius:999px;border:1px solid currentColor;white-space:nowrap}}
.chip.good{{color:var(--good)}}.chip.warning{{color:var(--warning)}}.chip.critical{{color:var(--critical)}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--text2);font-weight:600}}
.rowh{{color:var(--text);min-width:170px}}.scroll{{overflow-x:auto}}td.bad{{color:var(--critical);font-weight:650}}
pre{{background:var(--code);border-radius:6px;padding:10px;font-size:11px;overflow-x:auto;white-space:pre;margin:8px 0 0}}
.alert{{border-left:4px solid var(--critical)}}.alert ul{{padding-left:18px}}
footer{{color:var(--muted);font-size:12px;margin-top:32px}}
</style></head><body><main>
<h1>Client Report Delivery</h1>
<p class="sub">Monthly billing extracts for three enterprise clients, each in the format their own system requires. Every file is
parsed back and reconciled to the warehouse before it can be sent. Synthetic data, fictional company and clients.</p>
<div class="tiles">{tiles_html}</div>
<h2>Delivery status by client and period</h2>
<div class="card scroll"><p class="muted">Hover a cell for the reconciliation behind it.</p><table><tr><th></th>{head}</tr>{rows}</table></div>
<h2>Blocked before it reached the client</h2>
<div class="card alert">{blocked_html}</div>
<h2>Reconciliation for every delivery</h2>
<div class="card scroll"><p class="muted">Gap = source − file − held − excluded. Any gap other than $0.00 blocks the file.</p>
<table><tr><th>Period</th><th>Client</th><th>Status</th><th>Source</th><th>In file</th><th>Held</th><th>Excluded by contract</th><th>Gap</th><th>Due</th></tr>{recon}</table></div>
<h2>Held lines, most recent first</h2>
<div class="card scroll"><table><tr><th>Period</th><th>Client</th><th>Line</th><th>Job</th><th>Item</th><th>Amount</th><th>Reason</th></tr>{hold_rows}</table></div>
<h2>What each client receives ({periods[-1]})</h2>
<div class="grid3">{previews}</div>
<footer>Built from output/delivery_log.csv and output/summary.json.</footer></main></body></html>"""
    (OUT / "dashboard.html").write_text(page)
    print("wrote output/dashboard.html")


if __name__ == "__main__":
    main()
