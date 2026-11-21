# Optional pinned-loader source audit

This is a bounded source characterization, separate from portable quick host
checks. It requires the pinned NCS source, located through the `OMI_NCS_ROOT` environment variable,
Python3 and a host C compiler. It does not install dependencies, access keys,
build firmware, connect hardware or authorize any operation.

Run from the repository root:

```sh
OMI_NCS_ROOT=/path/to/ncs python3 -m unittest discover -s omi/firmware/tools/cv1/source_review -p 'test_*.py'
```

`matrix-result.json` is retained output bound to source hashes. The comparator
is extracted from actual pinned C and compiled on the host; other control flow
is a faithful Python characterization using an authentication oracle. 104
representative state classes per reachable version case are not 104 device tests
or exhaustive physical cut coverage. See ../../../docs/ota-bootstrap-contract.md
for assumptions, counterexample, proposed maps and implementation hold.
