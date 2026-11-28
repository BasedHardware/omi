#!/usr/bin/env python3
"""omi-support-ops: the audited operator CLI for customer support writes and data access.

Not the read-only ``omi-support`` harness CLI (``scripts/support/cli.py``, a support
person's own Firebase session against ``/v1/support/*``). This one runs on operator
cloud credentials, for holds, retention checks, DSAR exports and account operations.

    python scripts/support/ops.py --ticket T --actor A --reason R hold status UID
    python scripts/support/ops.py --ticket T --actor A --reason R hold place UID --review-by 2027-05-20 --apply
    python scripts/support/ops.py --ticket T --actor A --reason R hold release UID --apply
    python scripts/support/ops.py --ticket T --actor A --reason R hold list
    python scripts/support/ops.py --ticket T --actor A --reason R retention check UID [--conversation CID] [--month 2025-08]
    python scripts/support/ops.py --ticket T --actor A --reason R dsar export UID --approval NOTE_ID --apply
    python scripts/support/ops.py --ticket T --actor A --reason R account summary UID
    python scripts/support/ops.py --ticket T --actor A --reason R transcription-credit status UID
    python scripts/support/ops.py --ticket T --actor A --reason R transcription-credit grant UID --hours 30 [--expires-days 30] --apply
    python scripts/support/ops.py --ticket T --actor A --reason R transcription-credit revoke UID GRANT_ID --apply

Hold, retention, export and summary commands first write ``support_actions/{id}`` (ticket,
actor, agent, reason, command, argument digest) and finishes it with the outcome;
if that audit write fails the command does not run. Writes are dry runs unless
``--apply`` is passed. ``--agent`` (or ``SUPPORT_AGENT_ID``) names the operator
identity that ran the command; ``--actor`` is the human who asked for it.
Plan correction records its dry run in the private packet and creates a
per-owner audit document atomically with each plan write.

Runs with the operator's ADC (``prod-operator`` tier for production today; the
support operator service account once provisioned). Runbook:
``backend/docs/runbooks/support-operator-cli.md``.
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import socket
import sys
from pathlib import Path
from typing import Any, Callable, NoReturn

import google.auth

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from database import support_actions  # noqa: E402
from utils.support import account, dsar_export, holds, plan_correction, retention, transcription_credit  # noqa: E402

Handler = Callable[[argparse.Namespace, support_actions.ActionContext, support_actions.ActionRecord], dict[str, Any]]
MODULES = (holds, retention, dsar_export, account, transcription_credit)


def _adc_principal() -> str | None:
    """The service-account email (or ``user``) behind the operator's ADC, without a network call."""

    try:
        credentials, _project = google.auth.default()
    except Exception as exc:  # noqa: BLE001 - recorded, never fatal
        return f"unresolved:{type(exc).__name__}"
    email = getattr(credentials, "service_account_email", None) or getattr(credentials, "signer_email", None)
    if isinstance(email, str) and email and email != "default":
        return email
    return type(credentials).__name__


def _default_agent() -> str:
    return os.environ.get("SUPPORT_AGENT_ID") or f"{getpass.getuser()}@{socket.gethostname()}"


class _PrivateArgumentsParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        super().error("invalid plan correction arguments (see account correct-plan --help)")


def build_parser(*, private_arguments: bool = False) -> argparse.ArgumentParser:
    parser_type = _PrivateArgumentsParser if private_arguments else argparse.ArgumentParser
    parser = parser_type(prog="omi-support-ops", description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--ticket", required=True, help="Intercom conversation ID or issue reference")
    parser.add_argument("--actor", required=True, help="the human who asked for this action")
    parser.add_argument("--reason", required=True, help="why, in one line (no customer content)")
    parser.add_argument("--agent", default=None, help="operator identity that runs it (default SUPPORT_AGENT_ID)")
    parser.add_argument("--apply", action="store_true", help="perform writes (default: dry run)")
    groups = parser.add_subparsers(dest="group", required=True)
    for module in MODULES:
        module.register(groups)
    return parser


def _command_args(args: argparse.Namespace) -> dict[str, Any]:
    skip = {"ticket", "actor", "reason", "agent", "apply", "handler"}
    return {key: value for key, value in vars(args).items() if key not in skip}


def _hoist_apply(argv: list[str]) -> list[str]:
    """Accept ``--apply`` anywhere: argparse hands tokens after the subcommand to the leaf parser."""
    if "--apply" not in argv:
        return argv
    return ["--apply", *(token for token in argv if token != "--apply")]


def main(argv: list[str] | None = None, *, firestore_client: Any | None = None) -> int:
    tokens = _hoist_apply(list(sys.argv[1:] if argv is None else argv))
    args = build_parser(private_arguments='correct-plan' in tokens).parse_args(tokens)
    if getattr(args, 'plan_correction', False):
        previous_log_level = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            return _run_plan_correction(args, firestore_client=firestore_client)
        finally:
            logging.disable(previous_log_level)
    ctx = _context(args)
    command_args = _command_args(args)
    command = f"{args.group} {getattr(args, 'action', '')}".strip()
    handler: Handler = args.handler
    with support_actions.record_action(ctx, command, command_args, firestore_client=firestore_client) as record:
        result = handler(args, ctx, record)
    print(
        json.dumps({"action_id": record.action_id, "apply": ctx.apply, **result}, indent=1, sort_keys=True, default=str)
    )
    return 0


def _context(args: argparse.Namespace) -> support_actions.ActionContext:
    return support_actions.ActionContext(
        ticket=args.ticket,
        actor=args.actor,
        reason=args.reason,
        agent=args.agent or _default_agent(),
        apply=args.apply,
        principal=_adc_principal(),
    )


def _run_plan_correction(args: argparse.Namespace, *, firestore_client: Any | None) -> int:
    try:
        ctx = _context(args)
    except support_actions.SupportActionError:
        print(json.dumps({'document_reads': 0, 'counts': {}, 'error': 'invalid_action_context'}))
        return 1
    counts, status = plan_correction.run(args, ctx, firestore_client=firestore_client)
    print(json.dumps(counts, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
