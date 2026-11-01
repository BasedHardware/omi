#!/usr/bin/env python3
"""One day per Cloud Run execution, serial --wait, paused, resumable small batches.

Default prints 180 daily commands (no execution). --execute --batch-size 5 runs
only the first five; set --start/--days for the next batch. Same date is safe to retry.
"""

import argparse
import datetime as dt
import shlex
import subprocess
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--start', default=(dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=180)).isoformat())
    ap.add_argument('--days', type=int, default=180)
    ap.add_argument('--batch-size', type=int, default=5)
    ap.add_argument('--pause', type=int, default=30)
    ap.add_argument('--execute', action='store_true')
    a = ap.parse_args()
    start = dt.date.fromisoformat(a.start)
    today = dt.datetime.now(dt.timezone.utc).date()
    if (
        not 1 <= a.days <= 400
        or not 1 <= a.batch_size <= 10
        or a.pause < 5
        or start + dt.timedelta(days=a.days) > today
    ):
        ap.error('closed days only, 1..400 days, batch 1..10, pause >=5s')
    for i in range(min(a.days, a.batch_size) if a.execute else a.days):
        day = (start + dt.timedelta(days=i)).isoformat()
        cmd = [
            'gcloud',
            'run',
            'jobs',
            'execute',
            'omi-tv-rollup',
            '--project=based-hardware',
            '--region=us-central1',
            '--wait',
            f'--update-env-vars=OMI_TV_ROLLUP_DATE={day}',
        ]
        print(shlex.join(cmd), flush=True)
        if a.execute:
            subprocess.run(cmd, check=True)
            time.sleep(a.pause)


if __name__ == '__main__':
    main()
