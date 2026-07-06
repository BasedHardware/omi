---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_unregistrationerror
title: UnregistrationError Enum
scraped_at: 2026-07-03T14:24:24.370Z
---

# UnregistrationError Enum
Extends
Int, [DatError](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_daterror)
Error conditions that can occur during the unregistration process.
## Signature
```swift
enum UnregistrationError: Int, DatError
```
## Enumeration Constants
Member | Description |
alreadyUnregistered
|
User is already unregistered when attempting to unregister again.
|
configurationInvalid
|
The Wearables Device Access Toolkit configuration is invalid or incomplete.
|
metaAINotInstalled
|
The Meta AI app is not installed on the device, which is required for unregistration.
|
timeout
|
The registration process timed out. Please try again.
|
unknown
|
An unknown error occurred during the unregistration process.
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
