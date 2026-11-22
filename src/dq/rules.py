"""Rule definitions and the validator. Rules are config, not code."""
from dataclasses import dataclass, field

@dataclass
class Failure:
    record_id: str
    rule: str
    detail: str

@dataclass
class RuleResult:
    rule: str
    passed: int = 0
    failed: int = 0
    failures: list = field(default_factory=list)

def check_not_null(rows, column):
    r = RuleResult(rule=f"not_null:{column}")
    for row in rows:
        if row.get(column) in (None, ""):
            r.failed += 1
            r.failures.append(Failure(str(row.get("id", "?")), r.rule, f"{column} is null"))
        else:
            r.passed += 1
    return r

def check_unique(rows, column):
    r = RuleResult(rule=f"unique:{column}")
    seen = set()
    for row in rows:
        v = row.get(column)
        if v in seen:
            r.failed += 1
            r.failures.append(Failure(str(row.get("id", "?")), r.rule, f"duplicate {column}={v}"))
        else:
            seen.add(v)
            r.passed += 1
    return r

def check_range(rows, column, low, high):
    r = RuleResult(rule=f"range:{column}[{low},{high}]")
    for row in rows:
        try:
            v = float(row.get(column))
        except (TypeError, ValueError):
            r.failed += 1
            r.failures.append(Failure(str(row.get("id", "?")), r.rule, f"{column} is not numeric"))
            continue
        if low <= v <= high:
            r.passed += 1
        else:
            r.failed += 1
            r.failures.append(Failure(str(row.get("id", "?")), r.rule, f"{column}={v} out of range"))
    return r

def check_schema(rows, required):
    r = RuleResult(rule="schema")
    if not rows:
        r.failed += 1
        r.failures.append(Failure("batch", r.rule, "no rows"))
        return r
    missing = [c for c in required if c not in rows[0]]
    if missing:
        r.failed += 1
        r.failures.append(Failure("batch", r.rule, f"missing columns: {missing}"))
    else:
        r.passed += len(required)
    return r

def validate(rows, config):
    """Run every rule in config over rows. Returns (results, quarantined_ids)."""
    results = [check_schema(rows, config.get("required_columns", []))]
    for col in config.get("not_null", []):
        results.append(check_not_null(rows, col))
    for col in config.get("unique", []):
        results.append(check_unique(rows, col))
    for col, bounds in config.get("range", {}).items():
        results.append(check_range(rows, col, bounds[0], bounds[1]))
    quarantined = sorted({f.record_id for r in results for f in r.failures})
    return results, quarantined
