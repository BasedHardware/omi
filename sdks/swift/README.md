<!-- This file is auto-generated from docs/docs/docs/developer/sdk/swift.mdx. Do not edit manually. -->
### Omi Swift Library

An easy to install package to get started with the omi dev kit 1 in seconds.

## Installation

0. Open Xcode => File => New Project => Ios => App => Create project (Interface: storyboard

![CleanShot 2025-03-25 at 15 56 36@2x](https://github.com/user-attachments/assets/7e59be15-48dc-4ff1-bcf1-235b8bab3990)

1. In Xcode navigate to File → Swift Packages → Add Package Dependency...
2. Select a project
3. Paste the repository URL (https://github.com/BasedHardware/omi) and click Next.

If you aren't being asked to add the package to your target, click on "add Package" again, then "Add to Target" and choose your project

<img
  width="1407"
  alt="CleanShot 2025-03-25 at 16 15 29@2x"
  src="https://github.com/user-attachments/assets/5295b4df-81b6-49b2-80d8-67c43e2a31c2"
/>

4. install Requirement

Go to "Targets => your project => Info" and add this permission:

```xml
<key>NSBluetoothAlwaysUsageDescription</key>
<string>This app needs Bluetooth access to connect to BLE devices.</string>
```

## Run in 2 minutes

1. Copy this code into ViewController.swift

```
//
//  ViewController.swift
//  omi_demo
//
//

import UIKit
import omi_lib

class ViewController: UIViewController {

    override func viewDidLoad() {
        super.viewDidLoad()
        // Do any additional setup after loading the view.

        self.lookForDevice()
    }

    func lookForDevice() {
        OmiManager.startScan { device, error in
            // connect to first found omi device
            print("starting scan")
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

    func connectToOmiDevice(device: Device) {
        OmiManager.connectToDevice(device: device)
        self.listenToLiveTranscript(device: device)
        self.reconnectIfDisconnects()
    }

    func reconnectIfDisconnects() {
        OmiManager.connectionUpdated { connected in
            if connected == false {
                self.lookForDevice()
            }
        }
    }

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
}

```

2. Select your team, connect the phone (we suggest via cable), and run the project

3. turn on omi device - the app should connect automatically

Speak. You will not see any UI on the mobile app, but you should see transcription in logs. Transcription runs locally using whisper

![CleanShot 2025-03-25 at 16 00 43@2x](https://github.com/user-attachments/assets/636b33ac-7ea7-4e1c-b490-8ec99b1feef8)

## Other Usage

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

## Licensing

Omi's Swift SDK is available under MIT License
