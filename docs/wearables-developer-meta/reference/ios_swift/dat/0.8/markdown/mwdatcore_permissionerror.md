---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_permissionerror
title: PermissionError Enum
scraped_at: 2026-07-03T14:24:22.632Z
---

# PermissionError Enum
Extends
Int, [DatError](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_daterror)
Errors that can occur during permission requests.
## Signature
```swift
enum PermissionError: Int, DatError
```
## Enumeration Constants
Member | Description |
noDevice
|
No wearable devices have been discovered or registered.
|
noDeviceWithConnection
|
All discovered devices are powered off or disconnected.
|
connectionError
|
A connection error occurred while communicating with the device.
|
metaAINotInstalled
|
The Meta AI companion app is not installed on the device.
|
requestInProgress
|
A permission request is already in progress.
|
requestTimeout
|
The permission request exceeded the allowed time limit.
|
internalError
|
An unexpected internal error occurred.
|
## Properties
description
: String
[Get]
|
|
errorDescription
: String?
[Get]
|
|
