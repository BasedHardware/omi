---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatmockdevice_mockpermissions
title: MockPermissions Protocol
scraped_at: 2026-07-03T14:24:36.936Z
---

# MockPermissions Protocol
Extends
Sendable
Interface for configuring mock permission behavior during testing.
Use this to simulate granted/denied permission states and control the outcome of `requestPermission()` calls without launching the Meta AI companion app.
## Signature
```swift
protocol MockPermissions: Sendable
```
## Functions
set
(
permission
, status
)
|
Sets the status of a permission on the mock device.
This affects both `checkPermissionStatus()` (via the DataX service) and subsequent `requestPermission()` calls.
Signature
```swift
public func set(_ permission: Permission, _ status: PermissionStatus)
```
Parameters
`_ permission: [Permission](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_permission)`
The permission to configure.
`_ status: [PermissionStatus](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_permissionstatus)`
The status to assign to the permission.
|
setRequestResult
(
permission
, result
)
|
Configures the result that `requestPermission()` will return for a specific permission.
Signature
```swift
public func setRequestResult(_ permission: Permission, result: PermissionStatus)
```
Parameters
`_ permission: [Permission](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_permission)`
The permission to configure.
`result: [PermissionStatus](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcore_permissionstatus)`
The status to return when the permission is requested.
|
