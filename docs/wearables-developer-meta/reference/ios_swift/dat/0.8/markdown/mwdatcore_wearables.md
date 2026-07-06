---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearables
title: Wearables Enum
scraped_at: 2026-07-03T14:24:24.003Z
---

# Wearables Enum
The entry point for configuring and accessing the Wearables Device Access Toolkit.
Provides registration, device management, permissions, and session state functionality for interacting with AI glasses.
## Signature
```swift
enum Wearables
```
## Enumeration Constants
Member |
## Properties
shared
: [WearablesInterface](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearablesinterface)
[Get]
|
The shared Device Access Toolkit instance.
|
## Functions
configure
()
|
Configures the Wearables Device Access Toolkit with settings from the app bundle.
This method must be called once before accessing [shared](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearables#shared) or using any other Wearables Device Access Toolkit functionality. Subsequent calls will throw [WearablesError.alreadyConfigured](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_wearableserror#alreadyConfigured).
Signature
```swift
public static func configure()
```
Throws
|
