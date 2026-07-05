---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_thermallevel
title: ThermalLevel Enum
scraped_at: 2026-07-03T14:24:24.216Z
---

# ThermalLevel Enum
Extends
Sendable, Equatable
Represents the thermal level reported by the connected device.
The thermal level indicates the current temperature state of the glasses. Higher levels indicate progressively more severe thermal conditions, which may affect device performance or trigger protective shutdowns.
## Signature
```swift
enum ThermalLevel: Sendable, Equatable
```
## Enumeration Constants
Member | Description |
unknown
|
The thermal level is unknown or has not been reported.
|
none
|
No thermal concern.
|
light
|
Light thermal activity detected.
|
moderate
|
Moderate thermal activity — some features may be throttled.
|
severe
|
Severe thermal activity — significant throttling expected.
|
critical
|
Critical thermal level — device performance is heavily restricted.
|
emergency
|
Emergency thermal level — device is preparing for shutdown.
|
shutdown
|
The device is shutting down due to thermal conditions.
|
