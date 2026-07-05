---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_registrationstate
title: RegistrationState Enum
scraped_at: 2026-07-03T14:24:22.452Z
---

# RegistrationState Enum
Extends
Int
Represents the current state of user registration with the Meta Wearables platform.
## Signature
```swift
enum RegistrationState: Int
```
## Enumeration Constants
Member | Description |
unavailable
|
Registration is not available, typically due to system constraints.
|
available
|
Registration is available and can be initiated.
|
registering
|
Registration process is in progress.
|
registered
|
User is successfully registered with the platform.
|
## Properties
description
: String
[Get]
|
Provides a human-readable description of the registration state.
|
