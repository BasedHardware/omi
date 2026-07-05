---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_compatibility
title: Compatibility Enum
scraped_at: 2026-07-03T14:24:18.043Z
---

# Compatibility Enum
Extends
CaseIterable, Sendable
Indicates the compatibility status between AI glasses and the Wearables Device Access Toolkit.
This status reflects whether the device version is compatible with the currently installed Wearables Device Access Toolkit version, and whether any updates are required.
## Signature
```swift
enum Compatibility: CaseIterable, Sendable
```
## Enumeration Constants
Member | Description |
undefined
|
Unknown compatibility status.
Treat as incompatible. This typically occurs when the device is disconnected or the version is unavailable.
|
compatible
|
Device is fully compatible with the current Wearables Device Access Toolkit version.
All features are available and no updates are required.
|
deviceUpdateRequired
|
Device is outdated and requires an update.
The device should be updated to the latest version to work properly with this Wearables Device Access Toolkit. Some features may be unavailable until the update is complete.
|
sdkUpdateRequired
|
Wearables Device Access Toolkit version is outdated and requires an update.
The app should be updated to a newer version to work with this device's version. Some features may be unavailable until the update is complete.
|
## Properties
displayString
: String
[Get]
|
Provides a description of the compatibility status.
|
