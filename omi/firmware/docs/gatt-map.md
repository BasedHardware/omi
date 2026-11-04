# CV1 recovery diagnostics

Existing services, UUIDs and attribute order are unchanged. On a normal boot,
the new diagnostics service is appended after the existing application services.
In safe mode, only diagnostics plus Zephyr's static services (including DIS,
SMP and the configured BAS) are available. Advertising name/payload is unchanged;
read diagnostics to distinguish repair from recording.

Service `19B10040-E8F2-537E-4F6C-D104768A1214`, read characteristic
`19B10041-E8F2-537E-4F6C-D104768A1214`, no notifications/CCC. Snapshot v1 is 16
bytes, little endian; normal GATT offset reads are supported.

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 1 | Format version: 1 |
| 1 | 1 | Currently running safe mode (0/1) |
| 2 | 1 | Next-boot latch set (0/1); clears on completed DFU |
| 3 | 1 | Cached persistent bootstate: 0 unknown, 1 SAFE, 2 GOOD, 3 TRIAL |
| 4 | 4 | Retained boot attempt count; clears after healthy self-test/DFU |
| 8 | 4 | Raw Nordic RESETREAS captured before clear |
| 12 | 4 | Latch reason: 0 none, 1 crash loop, 2 held button, 3 simulation |

No phone repair UI is implemented here. Consumers must check version and
payload size. See [safe mode](safe-mode.md) for lifecycle, test plan and limits.
