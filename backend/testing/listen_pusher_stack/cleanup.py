"""Fail-closed cleanup of the stack's isolated POSIX child sessions.

No denial is interpreted as exit. In particular, Darwin's historical EPERM
incident remains unexplained; a failed signal retains the caller's child handle.
"""

from __future__ import annotations

import errno
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class CleanupFailure(RuntimeError):
    """Cleanup could not prove that the owned child and its group are gone."""


@dataclass
class Child:
    name: str
    process: subprocess.Popen[bytes]
    log_path: Path
    cwd: Path
    command_identity: str
    uid: int


@dataclass(frozen=True)
class Member:
    pid: int
    ppid: int
    pgid: int
    uid: int
    state: str
    sid: int | None
    command: str = ''
    sid_errno: int | None = None


def group_members(pgid: int) -> list[Member]:
    # Only numeric identities, executable basename and state are retained, never argv or
    # environment. A process can exit between the ps snapshot and getsid, even
    # when the observed state was not Z. Retain ESRCH as an explicitly unknown
    # SID with the original state: observation is not ownership authorization
    # or evidence that the group disappeared.
    result = subprocess.run(
        ['ps', '-axo', 'pid=,ppid=,pgid=,uid=,stat=,comm='],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    members = []
    for line in result.stdout.splitlines():
        pid, ppid, group, uid, state, command = line.split(maxsplit=5)
        if int(group) == pgid:
            sid_errno = None
            try:
                sid = os.getsid(int(pid))
            except ProcessLookupError as error:
                if error.errno != errno.ESRCH:
                    raise
                sid = None
                sid_errno = error.errno
            members.append(Member(int(pid), int(ppid), int(group), int(uid), state, sid, Path(command).name, sid_errno))
    return members


def stop_child(child: Child, evidence: Path, *, census: Callable[[int], list[Member]] | None = None) -> None:
    """Return only after wait/reap AND a separate proof of group absence.

    Popen was created with start_new_session=True: its PID is the original PGID
    and SID. Processes in that session descend from that child. Before *each*
    group signal we verify the entire observed membership has that SID and the
    launching UID. No signal is sent on missing, denied or foreign membership.
    A leader that has already been reaped never authorizes a descendant signal.
    """
    process = child.process
    pgid = process.pid
    stage = 'initial'
    census = census or group_members

    def record(event: str, **details) -> None:
        row = {
            'event': event,
            'stage': stage,
            'monotonic': time.monotonic(),
            'name': child.name,
            'pid': process.pid,
            'original_pgid': pgid,
            'original_sid': pgid,
            'launch_uid': child.uid,
            'launch_cwd': str(child.cwd),
            'command_identity': child.command_identity,
            'returncode': process.returncode,
            **details,
        }
        with evidence.open('a', encoding='utf-8') as output:
            output.write(json.dumps(row, sort_keys=True) + '\n')

    def members() -> list[Member]:
        rows = census(pgid)
        record('census', members=[vars(row) for row in rows])
        return rows

    def verify_ownership(rows: list[Member]) -> None:
        for row in rows:
            if row.pgid != pgid or row.sid != pgid or row.uid != child.uid:
                raise CleanupFailure(f'{child.name}: foreign or unverifiable group member pid={row.pid}')
            if row.pid == process.pid and row.ppid != os.getpid():
                raise CleanupFailure(f'{child.name}: leader is no longer our direct child')

    def prove_absent() -> None:
        # After reap, ask the kernel first. ESRCH alone proves group absence;
        # metadata is unnecessary on this path. EPERM is never absence. If the
        # group exists, retain its census only as diagnostics and refuse cleanup.
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            record('group_absent')
            return
        members()
        raise CleanupFailure(f'{child.name}: reaped leader has surviving group members or unknown membership')

    def send(sig: int) -> None:
        # Reap our exact direct child before metadata calls. A terminal leader
        # never authorizes signaling, even if its group still has descendants.
        status = process.poll()
        record('poll', status=status)
        if status is not None:
            prove_absent()
            return
        rows = members()
        # The child may have exited during ps/getsid regardless of the snapshot
        # state. Reap and prove absence rather than inventing its missing SID.
        status = process.poll()
        record('poll_after_census', status=status)
        if status is not None:
            prove_absent()
            return
        if sig == signal.SIGKILL and len(rows) == 1:
            row = rows[0]
            if (
                row.pid == process.pid
                and row.ppid == os.getpid()
                and row.pgid == pgid
                and row.uid == child.uid
                and row.sid is None
                and row.sid_errno == errno.ESRCH
            ):
                # Missing SID cannot authorize KILL, even if the snapshot looks
                # like an exiting child. Use the existing KILL wait allowance
                # solely to reap this exact retained child; neither its state
                # nor ESRCH proves exit. The caller must still prove absence.
                record('reap_only', reason='sole_direct_child_sid_unknown')
                return
        verify_ownership(rows)
        if not rows:
            raise CleanupFailure(f'{child.name}: live child missing from group census')
        # Keep an unreaped direct child as the ownership anchor. Reaped leaders
        # with remaining descendants require explicit investigation, not a
        # signal to a potentially reused group identity.
        if process.returncode is not None:
            raise CleanupFailure(f'{child.name}: reaped leader has surviving group members')
        record('signal', signal=int(sig))
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            record('signal_esrch', signal=int(sig))
        # PermissionError deliberately propagates, even if a later poll could
        # reap the child. No historical-EPERM recovery is authorized here.

    try:
        stage = 'poll'
        status = process.poll()
        record('poll', status=status)
        if status is None:
            stage = 'term'
            send(signal.SIGTERM)
            stage = 'wait_term'
            record('wait_begin')
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                record('wait_timeout')
                stage = 'kill'
                send(signal.SIGKILL)
                stage = 'wait_kill'
                record('wait_begin')
                process.wait(timeout=5)
            record('wait_reaped')
        stage = 'verify_absent'
        prove_absent()
        record('cleaned')
    except Exception as error:
        record('failed', error_type=type(error).__name__, errno=getattr(error, 'errno', None))
        raise CleanupFailure(
            f'{child.name}: cleanup failed at {stage}; pid/pgid={pgid}; '
            f'{type(error).__name__}: {error}; evidence={evidence}'
        ) from error
