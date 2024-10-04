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

The RootVC shows off an example of how to use OmiManager to connect to the Omi Friend Device.

**Looking for a device**
```swift
func lookForDevice() {
    OmiManager.startScan { device, error in
        // connect to first found omi device
        if let device = device {
            print("got device ", device.id.uuidString)
            self.connectToOmiDevice(device: device)
            OmiManager.endScan()
        }
    }
}

func lookForSpecificDevice(device_id: String) {
    OmiManager.startScan { device, error in
        // connect to an omi device with a specific id
        if let device = device, device.id.uuidString == device_id {
            self.connectToOmiDevice(device: device)
        }
    }
}
```

**Connecting / Reconnecting to a device**
```swift
func connectToOmiDevice(device: Friend) {
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
func listenToLiveTranscript(device: Friend) {
    OmiManager.getLiveTranscription(device: device) { transcription in

        self.full_transcript = self.full_transcript + "\(self.getFormattedTimestamp(for: Date())): " + (transcription ?? "" ) + "\n\n"

        DispatchQueue.main.async {
            self.textView.text = self.full_transcript
            if self.textView.text.count > 0 {
                Defaults.singleton.setDetailsForScribe(details: self.full_transcript)
            }
            
            let range = NSMakeRange(self.textView.text.count - 1, 1)
            self.textView.scrollRangeToVisible(range)
        }
    }
}

func listenToLiveAudio(device: Friend) {
    OmiManager.getLiveAudio(device: device) { file_url in
        print("file_url: ", file_url?.absoluteString ?? "no url")
    }
}
```

## Licensing

Omi's Swift SDK is available under MIT License

### Third-Party Code

An excerpt of code from the PAL project, licensed under the MIT License, is used in this project. The original code can be found at: [nelcea/PAL](https://github.com/nelcea/PAL).

- Copyright (c) 2024 Nelcea