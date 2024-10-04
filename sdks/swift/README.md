### Omi Swift Library
An easy to install package to get started with the omi dev kit 1 in seconds.


## Installation
1. In Xcode navigate to File → Swift Packages → Add Package Dependency...
2. Select a project
3. Paste the repository URL (https://github.com/ashbhat/omi.git) and click Next.
4. For Rules, select Version (Up to Next Major) and click Next.
5. Click Finish.

## Requirements
iOS requires you to include Bluetooth permissions in the info.plist. This can be done by adding the following row
```xml
<key>NSBluetoothAlwaysUsageDescription</key>
<string>This app needs Bluetooth access to connect to BLE devices.</string>
```

## Usage
The core interface for interacting with the Omi device is the **OmiManager.swift**. The OmiManager abstracts things like scanning, connecting, and reading bluetooth data into a few simple function calls.

**Looking for a device**
```swift
import omi_lib

func lookForDevice() {
    OmiManager.startScan { device, error in
        // connect to first found omi device
        if let device = device {
            print("got device ", device)
            self.connectToOmiDevice(device: device)
            OmiManager.endScan()
        }
    }
}

func lookForSpecificDevice(device_id: String) {
    OmiManager.startScan { device, error in
        // connect to first found omi device
        if let device = device, device.id == "some_device_id" {
            print("got device ", device)
            self.connectToOmiDevice(device: device)
            OmiManager.endScan()
        }
    }
}
```

**Connecting / Reconnecting to a device**
```swift
func connectToOmiDevice(device: Device) {
    OmiManager.connectToDevice(device: device)
    self.reconnectIfDisconnects()
}

func reconnectIfDisconnects() {
    OmiManager.connectionUpdated { connected in
        if connected == false {
            self.lookForDevice()
        }
    }
}
```

**Getting Live Data**
```swift
func listenToLiveTranscript(device: Device) {
    OmiManager.getLiveTranscription(device: device) { transcription in
        print("transcription:", transcription ?? "no transcription")
    }
}

func listenToLiveAudio(device: Device) {
    OmiManager.getLiveAudio(device: device) { file_url in
        print("file_url: ", file_url?.absoluteString ?? "no url")
    }
}
```

## TODO

- [] get live transcription working on this package; it's currently running into a bundle reference issue due to the monorepo nature of the repository

## Licensing

Omi's Swift SDK is available under MIT License

### Third-Party Code

An excerpt of code from the PAL project, licensed under the MIT License, is used in this project. The original code can be found at: [nelcea/PAL](https://github.com/nelcea/PAL).

- Copyright (c) 2024 Nelcea