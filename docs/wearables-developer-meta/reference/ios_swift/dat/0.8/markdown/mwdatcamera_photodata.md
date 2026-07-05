---
source: https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_photodata
title: PhotoData Struct
scraped_at: 2026-07-03T14:24:13.460Z
---

# PhotoData Struct
Extends
Sendable
A photo captured from a Meta Wearables device.
## Signature
```swift
struct PhotoData: Sendable
```
## Constructors
init
(
data
, format
)
|
Signature
```swift
public init( data: Data, format: PhotoCaptureFormat)
```
Parameters
`data: Data`
`format: [PhotoCaptureFormat](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_photocaptureformat)`
|
## Properties
data
: Data
|
The photo data in the specified format.
|
format
: [PhotoCaptureFormat](https://wearables.developer.meta.com/docs/reference/ios_swift/dat/0.8/mwdatcamera_photocaptureformat)
|
The format of the captured photo data.
|
