---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_registrationerror
title: RegistrationError Enum
scraped_at: 2026-07-03T14:24:23.153Z
---

# RegistrationError Enum
Extends
Int, [DatError](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_daterror)
Error conditions that can occur during the registration process.
## Signature
```swift
enum RegistrationError: Int, DatError
```
## Enumeration Constants
Member | Description |
alreadyRegistered
|
User is already registered when attempting to register again.
|
configurationInvalid
|
The Wearables Device Access Toolkit configuration is invalid or incomplete.
|
metaAINotInstalled
|
The Meta AI app is not installed on the device, which is required for registration.
|
networkUnavailable
|
Network connection is unavailable. Please check your internet connection and try again.
|
timeout
|
The registration process timed out. Please try again.
|
unknown
|
An unknown error occurred during the registration process.
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
