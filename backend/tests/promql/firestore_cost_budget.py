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
            operator = {"gt": ">", "lt": "<"}[threshold["type"]]
            expanded[node["refId"]] = f'({expanded[model["expression"]]}) {operator} {threshold["params"][0]}'
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


def unattributed_case(name, ratio, blind, absolute, excess, *, native_query="1800000x300", expect_blind=False):
    # 30,000 billed reads/s makes even a 600 reads/s gap only 2%.
    attributed = (30_000 - excess) * 60
    fires = excess > 579 and not expect_blind
    return {
        "name": name,
        "interval": "1m",
        "input_series": [
            counter("omi_firestore_billed_reads_by_caller_total", attributed),
            {"series": 'firestore_googleapis_com:document_read_count{type="LOOKUP"}', "values": "0x300"},
            {"series": 'firestore_googleapis_com:document_read_count{type="NOT_FOUND"}', "values": "0x300"},
            {"series": 'firestore_googleapis_com:document_read_count{type="QUERY"}', "values": native_query},
        ],
        "alert_rule_test": [
            {"eval_time": "115m", "alertname": absolute["title"], "exp_alerts": []},
            {"eval_time": "190m", "alertname": absolute["title"], "exp_alerts": [{}] if fires else []},
            {"eval_time": "190m", "alertname": ratio["title"], "exp_alerts": []},
            {"eval_time": "190m", "alertname": blind["title"], "exp_alerts": [{}] if expect_blind else []},
        ],
    }


def recording_case(name, *, hours=50, reads=50_000, breakouts=False, reset=False):
    ratio = "omi_batch_firestore_reads_per_completed_audio_hour"
    status = "omi_batch_firestore_cost_status"
    scope = 'project_id="based-hardware"'
    rows = []
    expected = []
    if hours is not None:
        # Two distinct original series exercise aggregation after increase().
        for outcome in ("speech", "confirmed_silence"):
            rows.append(
                counter(f'omi_batch_pipeline_completed_audio_seconds_total{{{scope},outcome="{outcome}"}}', hours * 30)
            )
    if reads is not None:
        rows.append(
            counter(
                f'omi_firestore_billed_reads_by_caller_total{{{scope},caller="database.batch_pipeline_store:get"}}',
                reads,
            )
        )
    if hours is not None and hours >= 50 and reads is not None:
        groups = {"batch": reads, "total": reads}
        if breakouts:
            for group, caller, rate in (
                ("lifecycle", "database.lifecycle_metrics_queries:nojob", 1000),
                ("erasure", "database.batch_pipeline_purge:purge_batch_owner", 500),
                ("packing_probe", "database.batch_pipeline_store:packing_candidates", 120),
            ):
                rows.append(counter(f'omi_firestore_billed_reads_by_caller_total{{{scope},caller="{caller}"}}', rate))
                groups[group] = rate
                if group != "packing_probe":
                    groups["total"] += rate
            rows.append(
                counter(
                    f'omi_firestore_billed_reads_by_origin_total{{{scope},origin="job:batch_packing_counterfactual"}}',
                    120,
                )
            )
        expected = [
            {"labels": f'{ratio}{{caller_group="{group}"}}', "value": rate * 60 / hours}
            for group, rate in groups.items()
        ]
    conditions = []
    if hours is not None and hours < 50:
        conditions.append("denominator_low")
    if hours is None or reads is None:
        conditions.append("telemetry_missing")
    if reset:
        # Restart inside the settled window with one minute already accumulated
        # on the new process. Increase must be computed on each raw counter.
        for row in rows:
            increment = row["values"].removeprefix("0+").removesuffix("x300")
            row["values"] = f"0+{increment}x149 {increment}+{increment}x150"
    return {
        "name": name,
        "interval": "1m",
        "input_series": rows,
        "promql_expr_test": [
            {"expr": ratio, "eval_time": "190m", "exp_samples": expected},
            {
                "expr": status,
                "eval_time": "190m",
                "exp_samples": [
                    {"labels": f'{status}{{condition="{condition}"}}', "value": 1} for condition in conditions
                ],
            },
        ],
    }


def coverage_case(name, second_query, expected):
    coverage = "omi_firestore_attributed_read_coverage_ratio_1h"
    native = 'firestore_googleapis_com:document_read_count{project_id="based-hardware",'
    return {
        "name": name,
        "interval": "1m",
        "input_series": [
            counter('omi_firestore_billed_reads_total{project_id="based-hardware"}', 300),
            {"series": native + 'type="LOOKUP"}', "values": "100x60"},
            {"series": native + 'type="NOT_FOUND"}', "values": "0x60"},
            {"series": native + 'type="QUERY",database_id="primary"}', "values": "100x60"},
            {"series": native + 'type="QUERY",database_id="secondary"}', "values": second_query},
        ],
        "promql_expr_test": [{"expr": coverage, "eval_time": "65m", "exp_samples": expected}],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--promtool", required=True, type=Path)
    args = parser.parse_args()
    rules_by_uid = {rule["uid"]: rule for rule in json.loads((MONITORING / "alerts/firestore.json").read_text())}
    step = rules_by_uid["omi-firestore-billed-reads-step"]
    ratio = rules_by_uid["omi-firestore-unattributed-reads"]
    blind = rules_by_uid["omi-firestore-unattributed-reads-blind"]
    absolute = rules_by_uid["omi-firestore-unattributed-absolute"]
    rules = [
        rules_by_uid["omi-firestore-batch-reads-audio-hour"],
        rules_by_uid["omi-firestore-batch-reads-no-output"],
        step,
        ratio,
        blind,
        absolute,
    ]
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
        unattributed_case("absolute fires at a 2% gap after two hours", ratio, blind, absolute, 600),
        unattributed_case("absolute stays quiet at 579 reads/s", ratio, blind, absolute, 579),
        unattributed_case("absolute stays quiet below threshold", ratio, blind, absolute, 578),
        unattributed_case(
            "missing native QUERY leaves coverage to blind",
            ratio,
            blind,
            absolute,
            600,
            native_query="_x300",
            expect_blind=True,
        ),
        unattributed_case(
            "stale native QUERY leaves coverage to blind",
            ratio,
            blind,
            absolute,
            600,
            native_query="1800000x15 _x285",
            expect_blind=True,
        ),
        recording_case("recorded ratio and disjoint groups", breakouts=True),
        recording_case("raw counter resets preserve the recorded ratio", reset=True),
        recording_case("recorded ratio retains an observed true zero", reads=0),
        recording_case("low completion volume suppresses ratio", hours=49),
        recording_case("observed zero completion volume is low", hours=0),
        recording_case("missing completions suppress ratio", hours=None),
        recording_case("missing reads suppress ratio", reads=None),
        coverage_case(
            "native coverage accepts a second series with 58 samples",
            "100x56 _ _ _ 100",
            [{"labels": "omi_firestore_attributed_read_coverage_ratio_1h", "value": 1}],
        ),
        coverage_case("native coverage rejects a second series with 57 samples", "100x55 _ _ _ _ 100", []),
    ]
    median = step["data"][1]["model"]["expr"]
    hourly = step["data"][0]["model"]["expr"]
    # GMP rejected offsets on the raw selectors inside these hourly subqueries.
    # Execute the committed outer-offset form and all seven daily offsets here;
    # production compatibility still requires the exact-head GMP readback.
    tests.append(
        {
            "name": "GMP outer-offset regression preserves current and seven-day raw totals",
            "interval": "1m",
            "input_series": [
                {"series": 'firestore_googleapis_com:document_read_count{type="QUERY"}', "values": "100x11519"},
                {"series": 'firestore_googleapis_com:document_read_count{type="LOOKUP"}', "values": "0x11519"},
                {"series": 'firestore_googleapis_com:document_read_count{type="NOT_FOUND"}', "values": "0x11519"},
            ],
            "promql_expr_test": [
                {"expr": query, "eval_time": "7d16h30m", "exp_samples": [{"labels": "{}", "value": 6100}]}
                for query in (hourly, median)
            ],
        }
    )
    for name, values, query, expected in (
        (
            "one missing minute is not extrapolated on pinned inclusive engine",
            "100x29 _ 100x28",
            hourly,
            [{"labels": "{}", "value": 6000}],
        ),
        (
            "58 raw minutes accepted without extrapolation on pinned inclusive engine",
            "100x27 _ _ _ 100x28",
            hourly,
            [{"labels": "{}", "value": 5800}],
        ),
        ("57 raw minutes reject current hour", "100x26 _ _ _ _ 100x28", hourly, []),
        ("missing baseline minutes reject median", "100x26 _ _ _ _ 100x28", median, []),
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
    recording = yaml.safe_load((MONITORING / "batch-cost/recording-rules.yaml").read_text())["spec"]["groups"]
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
                    + recording
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
