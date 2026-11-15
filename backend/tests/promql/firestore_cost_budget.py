"""Evaluate the committed cost expressions against real Prometheus fixtures."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

import yaml

MONITORING = Path(__file__).resolve().parents[2] / "charts/monitoring"


def expression(rule):
    expanded = {}
    for node in rule["data"]:
        model = node["model"]
        if "expr" in model:
            expanded[node["refId"]] = model["expr"]
        elif model["type"] == "math":
            math = model["expression"].replace("&&", "and")
            expanded[node["refId"]] = re.sub(r"\$([A-Z])", lambda match: "(" + expanded[match[1]] + ")", math)
        else:
            threshold = model["conditions"][0]["evaluator"]
            assert threshold["type"] == "gt"
            expanded[node["refId"]] = f'({expanded[model["expression"]]}) > {threshold["params"][0]}'
    return expanded[rule["condition"]]


def counter(name, per_minute):
    return {"series": name, "values": f"0+{per_minute}x300"}


def batch_case(name, reads, hours, expected, *, missing_output=False):
    rows = [
        counter('omi_firestore_billed_reads_by_caller_total{caller="database.batch_pipeline_store:get"}', reads / 120),
        counter('omi_firestore_billed_reads_by_caller_total{caller="utils.batch_pipeline_privacy:read"}', reads / 120),
        counter('omi_firestore_billed_reads_by_caller_total{caller="database.users:get"}', 1e9),
    ]
    if not missing_output:
        rows.append(counter("omi_batch_pipeline_completed_audio_seconds_total", hours * 60))
    return {
        "name": name,
        "interval": "1m",
        "input_series": rows,
        "alert_rule_test": [
            {"eval_time": "190m", "alertname": title, "exp_alerts": [{}] if title in expected else []}
            for title in ("FirestoreBatchReadsPerAudioHourHigh", "FirestoreBatchReadsWithNoOutput")
        ],
    }


def step_case(name, elevated, expected):
    daily = "100x779 200x59 100x599"
    final = "100x779 " + ("300x179 100x479" if elevated else "200x59 100x599")
    return {
        "name": name,
        "interval": "1m",
        "input_series": [
            {"series": 'firestore_googleapis_com:document_read_count{type="LOOKUP"}', "values": "0x11519"},
            {"series": 'firestore_googleapis_com:document_read_count{type="NOT_FOUND"}', "values": "0x11519"},
            {
                "series": 'firestore_googleapis_com:document_read_count{type="QUERY"}',
                "values": " ".join([daily] * 7 + [final]),
            },
        ],
        "alert_rule_test": [
            {"eval_time": "7d16h30m", "alertname": "FirestoreBilledReadsStep", "exp_alerts": [{}] if expected else []}
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--promtool", required=True, type=Path)
    args = parser.parse_args()
    rules = json.loads((MONITORING / "alerts/firestore.json").read_text())[-3:]
    tests = [
        batch_case("high ratio", 7800000, 100, {"FirestoreBatchReadsPerAudioHourHigh"}),
        batch_case("exact ratio boundary", 6000000, 100, set()),
        batch_case("fifty hours belongs to ratio", 3900000, 50, {"FirestoreBatchReadsPerAudioHourHigh"}),
        batch_case("low output high reads", 11000000, 49, {"FirestoreBatchReadsWithNoOutput"}),
        batch_case("zero output high reads", 11000000, 0, {"FirestoreBatchReadsWithNoOutput"}),
        batch_case("missing output high reads", 11000000, 0, {"FirestoreBatchReadsWithNoOutput"}, missing_output=True),
        batch_case("exact read boundary", 10000000, 0, set()),
        step_case("diurnal same hour stays quiet", False, False),
        step_case("full hour step sustained", True, True),
    ]
    median = rules[-1]["data"][1]["model"]["expr"]
    hourly = rules[-1]["data"][0]["model"]["expr"]
    for name, values, query, expected in (
        ("one missing minute is not extrapolated", "100x29 _ 100x28", hourly, [{"labels": "{}", "value": 5900}]),
        (
            "58 raw minutes accepted without extrapolation",
            "100x28 _ _ 100x28",
            hourly,
            [{"labels": "{}", "value": 5800}],
        ),
        ("57 raw minutes reject current hour", "100x27 _ _ _ 100x28", hourly, []),
        ("missing baseline minutes reject median", "100x27 _ _ _ 100x28", median, []),
        ("zero baseline rejects division", "0x59", median, []),
    ):
        tests.append(
            {
                "name": name,
                "interval": "1m",
                "input_series": [
                    {
                        "series": 'firestore_googleapis_com:document_read_count{type="QUERY"}',
                        "values": " ".join([values] * 192),
                    },
                    {"series": 'firestore_googleapis_com:document_read_count{type="LOOKUP"}', "values": "0x11519"},
                    {"series": 'firestore_googleapis_com:document_read_count{type="NOT_FOUND"}', "values": "0x11519"},
                ],
                "promql_expr_test": [{"expr": query, "eval_time": "7d16h30m", "exp_samples": expected}],
            }
        )
    for name, values in (
        ("one missing baseline day", " ".join(["100x1439"] * 3 + ["_x1439"] + ["100x1439"] * 4)),
        ("all baseline days missing", "_x10079 100x1439"),
    ):
        tests.append(
            {
                "name": name,
                "interval": "1m",
                "input_series": [
                    {"series": 'firestore_googleapis_com:document_read_count{type="LOOKUP"}', "values": "0x11519"},
                    {"series": 'firestore_googleapis_com:document_read_count{type="NOT_FOUND"}', "values": "0x11519"},
                    {"series": 'firestore_googleapis_com:document_read_count{type="QUERY"}', "values": values},
                ],
                "promql_expr_test": [{"expr": median, "eval_time": "7d16h30m", "exp_samples": []}],
            }
        )
    with tempfile.TemporaryDirectory(prefix="firestore-cost-promql-") as directory:
        root = Path(directory)
        (root / "rules.yml").write_text(
            yaml.safe_dump(
                {
                    "groups": [
                        {
                            "name": "firestore-cost",
                            "interval": "5m",
                            "rules": [
                                {"alert": rule["title"], "expr": expression(rule), "for": rule["for"]} for rule in rules
                            ],
                        }
                    ]
                }
            )
        )
        (root / "tests.yml").write_text(
            yaml.safe_dump(
                {
                    "rule_files": ["rules.yml"],
                    "evaluation_interval": "5m",
                    "tests": tests,
                }
            )
        )
        subprocess.run([str(args.promtool.resolve()), "test", "rules", "tests.yml"], cwd=root, check=True)


if __name__ == "__main__":
    main()
