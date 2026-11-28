"""Publish failed pytest node IDs in the GitHub Actions shard summary."""

from html import escape
import os
import sys

import pytest


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary and report.failed:
        node_id = escape(report.nodeid.replace('\r', r'\r').replace('\n', r'\n'))
        # Each isolated process (or xdist worker) appends one line per failure.
        try:
            with open(summary, 'a', encoding='utf-8') as stream:
                stream.write(f'- <code>{node_id}</code> ({report.when})\n')
        except OSError as error:
            print(f'Could not append shard failure summary: {error}', file=sys.stderr)
    return report
