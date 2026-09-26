#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Decide how CI can reach a public-build candidate for browser acceptance.

A no-traffic Cloud Run candidate is normally smoked through its tagged run.app
URL. That URL answers 404 to CI, authenticated or not, when the service's
ingress admits only internal or load-balancer traffic. The frontend behind
h.omi.me restricts ingress deliberately so the shared-chat rate-limit subject
can trust the balancer's X-Forwarded-For, which left every prod frontend
promotion failing with "canary did not become ready" since that flag landed.

Such a service can only be observed through its public hostname, which serves
whatever revision currently holds traffic. The promotion action therefore
promotes first, smokes the declared public URL, and rolls back on failure.
This helper is the single place that turns (target, environment, ingress) into
that decision, so an unreachable candidate fails naming the ingress policy.

Subcommands:
  route             emit route=candidate_url|public_url and public_url=...
  serving-revision  read a `gcloud run services describe --format=json`
                    document on stdin and print the revision holding traffic
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from check_public_build_contract import DEFAULT_CONTRACT, acceptance_route, load_contract, serving_revision


def _write_outputs(path: Path | None, outputs: dict[str, str]) -> None:
    lines = "".join(f"{key}={value}\n" for key, value in outputs.items())
    sys.stdout.write(lines)
    if path is not None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    route = subparsers.add_parser("route", help="resolve the acceptance route for one target and environment")
    route.add_argument("--target", required=True)
    route.add_argument("--environment", required=True)
    route.add_argument("--ingress", required=True, help="value of the run.googleapis.com/ingress annotation")
    route.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    route.add_argument("--github-output", type=Path, default=None)

    serving = subparsers.add_parser("serving-revision", help="print the revision holding the largest traffic share")
    serving.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT, help=argparse.SUPPRESS)

    args = parser.parse_args(argv)
    if args.command == "serving-revision":
        try:
            document = json.load(sys.stdin)
        except json.JSONDecodeError:
            print("serving-revision expects a Cloud Run service JSON document on stdin", file=sys.stderr)
            return 1
        print(serving_revision(document if isinstance(document, dict) else {}))
        return 0

    try:
        contract = load_contract(args.contract)
        target = contract.targets.get(args.target)
        if target is None:
            raise ValueError(f"unknown public-build target {args.target!r}")
        if args.environment not in contract.environments:
            raise ValueError(f"unknown public-build environment {args.environment!r}")
        resolved = acceptance_route(target, environment=args.environment, ingress=args.ingress)
    except ValueError as error:
        print(f"public-build acceptance route unavailable: {error}", file=sys.stderr)
        return 1
    _write_outputs(args.github_output, {"route": resolved.route, "public_url": resolved.public_url})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
