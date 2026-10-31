#!/usr/bin/env python3
"""Compute screening metrics from human-reviewed CSV using the standard library."""
import argparse
import csv
import json
import math
from pathlib import Path


def metric(n, d, interval=False):
    result = {"numerator": n, "denominator": d, "value": n / d if d else None}
    if interval:
        bounds = None
        if d:
            z = 1.959963984540054
            p = n / d
            center = (p + z*z/(2*d)) / (1 + z*z/d)
            half = z*math.sqrt(p*(1-p)/d + z*z/(4*d*d)) / (1 + z*z/d)
            bounds = [max(0, center-half), min(1, center+half)]
        result["wilson_95"] = bounds
    return result


def evaluate(path):
    predictions = ("qualified", "rejected", "needs_review")
    labels = ("suitable", "unsuitable", "insufficient")
    required = {"case_id", "prediction", "gold_label", "hard_violation", "factual_claims", "supported_claims"}
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV missing required columns")
        rows, seen = [], set()
        for line, raw in enumerate(reader, 2):
            if None in raw or any(raw.get(k) is None for k in required):
                raise ValueError(f"line {line}: malformed CSV row")
            row = {k: (v or "").strip() for k, v in raw.items()}
            if not row["case_id"] or row["case_id"] in seen:
                raise ValueError(f"line {line}: missing or duplicate case_id")
            seen.add(row["case_id"])
            if row["prediction"] not in predictions or row["gold_label"] not in labels:
                raise ValueError(f"line {line}: invalid prediction or gold_label")
            if row["hard_violation"] not in ("true", "false", "unknown"):
                raise ValueError(f"line {line}: invalid hard_violation")
            counts = [row["factual_claims"], row["supported_claims"]]
            if bool(counts[0]) != bool(counts[1]):
                raise ValueError(f"line {line}: provide both claim counts or neither")
            row["audited"] = bool(counts[0])
            try:
                total, supported = [int(x) if x else 0 for x in counts]
            except ValueError as exc:
                raise ValueError(f"line {line}: claim counts must be integers") from exc
            if not 0 <= supported <= total:
                raise ValueError(f"line {line}: expected 0 <= supported <= total")
            row.update(factual_claims=total, supported_claims=supported)
            rows.append(row)
    qualified = [r for r in rows if r["prediction"] == "qualified"]
    tp = sum(r["gold_label"] == "suitable" for r in qualified)
    known = sum(r["gold_label"] != "insufficient" for r in qualified)
    matrix = {p: {g: sum(r["prediction"] == p and r["gold_label"] == g for r in rows) for g in labels} for p in predictions}
    return {
        "sample_count": len(rows),
        "precision": metric(tp, known, True),
        "qualified_label_coverage": metric(known, len(qualified)),
        "conservative_suitable_share": metric(tp, len(qualified)),
        "recall": metric(tp, sum(r["gold_label"] == "suitable" for r in rows), True),
        "needs_review_rate": metric(sum(r["prediction"] == "needs_review" for r in rows), len(rows)),
        "hard_violation_rate": metric(sum(r["hard_violation"] == "true" for r in qualified), len(qualified)),
        "qualified_hard_audit_coverage": metric(sum(r["hard_violation"] != "unknown" for r in qualified), len(qualified)),
        "evidence_support_rate": metric(sum(r["supported_claims"] for r in rows), sum(r["factual_claims"] for r in rows)),
        "claim_audit_row_coverage": metric(sum(r["audited"] for r in rows), len(rows)),
        "confusion_matrix": matrix,
        "limitations": ["Labels and evidence audits are user-provided, not independently verified.", "Incomplete audit coverage prevents a complete quality conclusion.", "Demo or small-sample results do not establish business effectiveness."]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(args.csv_path)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Evaluation failed: {exc}\n")
    content = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
