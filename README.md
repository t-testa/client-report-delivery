# Client Report Delivery

**Recurring billing extracts for enterprise clients, each in the format their own system requires, with a reconciliation gate that blocks any file that doesn't account for every dollar.**

Large clients of a services marketplace don't want a dashboard. They want a file that drops into *their* system every month: a LEDES e-billing invoice for one law firm, a CSV in another firm's case-management import template, a JSON payload for an insurer's accounting system. Each has its own rules. One rejects lines without a matter number; another pays court fees directly and must never be billed for them.

The hard part isn't writing the files. It's knowing that a file is **complete and correct before it leaves**, and when it isn't, knowing exactly why.

```
warehouse (line_items, jobs, clients)
   │
   ├── source of truth: every billed line for the client and period (line items only, duplicates removed)
   │
   └── extract: lines joined to jobs, then the client's rules
            ├── excluded by contract  (e.g. court fees the client pays directly)  → reason recorded
            ├── held                  (no matter number, amount ≠ units × rate)   → reason recorded
            └── delivered             → written in the client's format
                                           │
                    parse the file back ◄──┘
                                           │
     reconcile: source = file + held + excluded, to the cent, and line counts match;
                the file passes its own format validation
                                           │
                 pass → outbox, with a note for the account manager if anything was held
                 fail → blocked, never sent, with the missing line IDs and a diagnosis
```

![dashboard](docs/dashboard.png)

## Results on the synthetic data

Three fictional clients, six monthly periods (May to October 2026), 18 deliveries, $104,725.65 billed.

| | |
|---|---|
| Files sent | 17 of 18: 4 clean, 13 with lines held for a fix |
| **Unexplained gap in any sent file** | **$0.00**: every dollar is in the file, held with a reason, or excluded by contract |
| Blocked before sending | 1: Bramwell Cardenas, August, $439.64 gap |
| Held for a fix | 28 lines, $1,423.73: 20 where the amount didn't equal units × rate, 8 with no matter number for clients that require one |
| Excluded by contract | $1,912.50 of court fees Northgate pays directly |
| Duplicate loads removed | 12 lines, before any totals |

**The blocked file is the point.** In August, seven line items were billed before their job records synced to the jobs table. The extract needs the job (matter number, dates), so the inner join silently dropped them. The file looked fine and was internally consistent. Only comparing it with the source totals, computed from line items alone, showed $439.64 missing. The pipeline blocked the file, listed the seven line IDs, and confirmed from the data that all seven belonged to jobs missing from the jobs table.

## The three clients

| Client | Their system | Format | Their rules |
|---|---|---|---|
| Hartwell & Lowe LLP | e-billing | **LEDES 1998B**: pipe-delimited, 24 fields, `[]` terminators, one invoice per matter, UTBMS expense codes they chose | matter number required |
| Bramwell Cardenas | case management | **CSV** in their import template: their column names and order, MM/DD/YYYY dates, their status words ("Non-Est") | matter number required, one row per job |
| Northgate Insurance Legal | accounting | **JSON** payload with claims and line items | matter optional; court fees excluded by contract |

Each client is one file, `clients/<client>/delivery.yaml`. Adding a client or changing a format is configuration, not code; a test builds a new client from config alone.

## Why it's built this way

**The source of truth doesn't depend on the extract.** Source totals come from line items only. The extract joins to jobs because it needs more fields. If both used the same query, a join that loses rows would lose them on both sides, and the check would pass. Keeping them independent is what caught the August gap.

**Reconcile the file you send, not the data you meant to send.** Every writer has a matching parser. The gate re-reads the actual LEDES, CSV or JSON, recomputes totals and validates the format: field count, date formats, expense codes, invoice total equal to the sum of its lines, units × rate equal to each line total. A test tampers with one LEDES line total and confirms it's caught.

**Nothing disappears without a reason.** Every source line ends up delivered, held or excluded, and the last two always carry a reason. Holds are client-specific, because the constraints of each client's system are different: a missing matter number blocks a line for Hartwell and Bramwell, but not for Northgate.

**Separate what the client needs to do from what we need to fix.** The note for each delivery splits held lines into a message the account manager can send ("reply with the matter number for these jobs") and an internal list for billing ops (amount errors the client should never see). Every figure in a note is checked against the run's numbers before it's written; Claude can polish the wording when an API key is set, and its draft is rejected if it changes any figure.

## Run it

```bash
pip install -r requirements.txt
python generate_data.py      # synthetic warehouse: clients, jobs, line items
python run.py                # 18 deliveries → output/outbox, output/blocked, logs, notes
python build_dashboard.py    # output/dashboard.html
pytest -q                    # 9 tests
```

## Layout

| Path | What it is |
|---|---|
| `sql/warehouse.sql` | DuckDB views: de-duplicated lines, source totals, extract lines |
| `clients/<client>/delivery.yaml` | the client's format, rules, codes and due date |
| `delivery/formats.py` | writers, parsers and validators for LEDES 1998B, CSV and JSON |
| `delivery/pipeline.py` | build one delivery: exclusions, holds, file, reconciliation gate, diagnosis |
| `delivery/notes.py` | account-manager and internal notes, with a figure check |
| `output/outbox/`, `output/blocked/` | files that would be sent, and the one that was stopped |
| `output/delivery_log.csv` | one row per delivery with every check and its result |

## Limitations

- **Synthetic data**, generated with seeded noise. Real client feeds will fail in ways this doesn't model.
- **LEDES coverage is expense lines only** (type `E`), because the services billed here are expenses to the law firm. Fee lines, adjustments and LEDES 2000/XML are not implemented.
- **Due dates count business days without a holiday calendar.** August's due date lands on Labour Day; a real version needs provincial and state holidays.
- **Delivery is to a local outbox.** SFTP, e-billing portal uploads and client acknowledgements are out of scope.
- **The Claude path for notes has not been run against a live model here;** the template path is what produced the committed notes.

## If I were running this team

- **Make the gate the definition of done.** No file goes out without a passing reconciliation, and the delivery log is the team's scorecard: accuracy, holds by cause, files blocked, on-time rate.
- **Fix causes, not files.** August's block points at the job sync, not the extract. Holds by cause show where upstream data needs work: here, units × rate errors are the biggest source.
- **Keep client formats as configuration** so the team spends time on client problems, not one-off scripts.
- **Automate the boring parts next:** scheduled runs after period close, supplementary files when a held line is fixed, and alerts when a file is blocked within days of its due date.

All data is synthetic. Docket Courier, Hartwell & Lowe, Bramwell Cardenas, Northgate Insurance Legal and every case and job are fictional.
