# CV1 GATT allocation map

Base UUID suffix: `-E8F2-537E-4F6C-D104768A1214`. Decided by the firmware lead on 2026-11-02 to end collisions between open PRs. A new characteristic takes the next free slot here in the same change that adds it. Claims come from the PR diffs; nothing below the "On main" group has been tested on hardware.

## On main

| UUID | Use |
|---|---|
| `19B10000`-`03` | Audio service, data, codec, speaker |
| `19B10010`-`13` | Settings service, dim ratio, mic gain, charging status |
| `19B10020`-`21` | Features service and bitmask |
| `19B10030`-`32` | Time sync service, write, read |

`19B10005` and `06` are image characteristics, and `19B10010`-`12` also name the omiGlass OTA service in the app. Don't reuse `19B10005` or `06` on CV1.

## Allocated to open PRs

| UUID | Use | PR | Other claimants that must move or close |
|---|---|---|---|
| `19B10014` | Device name | #23743 | #14289, #23938, #13704 are duplicates. #23735 and #10604 must move. |
| `19B10015` | Capture mute | #14293 | #13182 expects rename here. #10604 must move. |
| `19B10016` | Power off and pause | #23735, rebased | Moves off `14`. #10604 used this for rename. |
| `19B10040`-`41` | Device diagnostics, 25 bytes | #19469, in #24381 | #20483 keeps only its SoC freeze and battery work, with no characteristic of its own at this UUID. |

## Reserved, not decided

| UUID | Use | Waiting on |
|---|---|---|
| `19B10004` | Connected retention | #20838, only if the retention decision picks it over #20450, which adds no UUID |
