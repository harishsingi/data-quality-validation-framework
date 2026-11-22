"""Generate synthetic records. No real data."""
import csv, random
from pathlib import Path
random.seed(42)

def main():
    out = Path("data/records.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "customer_id", "amount", "updated_at"])
        w.writeheader()
        for i in range(1, 101):
            w.writerow({"id": i, "customer_id": f"C{i:04d}", "amount": random.randint(10, 900), "updated_at": f"2026-11-{i % 28 + 1:02d}T10:00:00Z"})
        # bad records, to exercise quarantine
        w.writerow({"id": 101, "customer_id": "", "amount": 50, "updated_at": "2026-11-22T10:00:00Z"})
        w.writerow({"id": 102, "customer_id": "C0102", "amount": 99999, "updated_at": "2026-11-22T10:00:00Z"})
        w.writerow({"id": 102, "customer_id": "C0102", "amount": 20, "updated_at": "2026-11-22T10:00:00Z"})
    print("wrote 103 synthetic records (3 bad, to exercise quarantine)")

if __name__ == "__main__":
    main()
