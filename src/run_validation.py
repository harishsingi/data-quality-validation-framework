"""CLI: python -m src.run_validation --dataset data/records.csv --rules rules/orders.yaml"""
import argparse, csv, json
from pathlib import Path
import yaml
from src.dq.rules import validate
from src.dq.freshness import check_freshness
from src.dq.quarantine import write_quarantine

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="data/records.csv")
    p.add_argument("--rules", default="rules/orders.yaml")
    a = p.parse_args()
    rows = list(csv.DictReader(open(a.dataset)))
    config = yaml.safe_load(open(a.rules))
    results, quarantined = validate(rows, config)
    for r in results:
        print(f"{r.rule}: {'PASS' if not r.failed else 'FAIL'} ({r.passed} passed, {r.failed} failed)")
    ok, msg = check_freshness(rows, expected_date=config.get("expected_date"))
    print(f"freshness: {'PASS' if ok else 'FAIL'} ({msg})")
    n_quarantined_rows = 0
    if quarantined:
        n_quarantined_rows = write_quarantine(rows, [f for r in results for f in r.failures], "data/quarantine.csv")
        print(f"quarantined {n_quarantined_rows} records to data/quarantine.csv (never to gold)")
    print(json.dumps({"total": len(rows), "quarantined_ids": len(quarantined), "quarantined_rows": n_quarantined_rows}, indent=2))

if __name__ == "__main__":
    main()
