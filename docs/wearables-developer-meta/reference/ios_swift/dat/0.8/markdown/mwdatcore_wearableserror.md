---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearableserror
title: WearablesError Enum
scraped_at: 2026-07-03T14:24:24.303Z
---

# WearablesError Enum
Extends
Int, [DatError](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_daterror)
Errors that can occur during Device Access Toolkit configuration.
## Signature
```swift
enum WearablesError: Int, DatError
```
## Enumeration Constants
Member | Description |
internalError
|
An unexpected internal error occurred during configuration.
|
alreadyConfigured
|
The Device Access Toolkit has already been configured.
|
configurationError
|
The configuration provided is invalid or incomplete.
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
