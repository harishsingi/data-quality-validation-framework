"""Quarantine writer: failed records never reach gold, with the reason attached."""
import csv
from pathlib import Path

def write_quarantine(rows, failures, out_path):
    bad_ids = {f.record_id for f in failures}
    bad = [r for r in rows if str(r.get("id", "?")) in bad_ids]
    reason = {f.record_id: f"{f.rule}: {f.detail}" for f in failures}
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) + ["quarantine_reason"] if rows else ["id", "quarantine_reason"])
        w.writeheader()
        for r in bad:
            w.writerow({**r, "quarantine_reason": reason.get(str(r.get("id", "?")), "")})
    return len(bad)
