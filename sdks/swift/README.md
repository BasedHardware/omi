<!-- This file is auto-generated from docs/doc/developer/sdk/swift.mdx. Do not edit manually. -->
## Overview

An easy-to-install Swift package for connecting to Omi devices. Get started in seconds with local Whisper-based transcription - no cloud API required.

<CardGroup cols={3}>
  <Card title="Swift Package" icon="swift">
    Native iOS/macOS support
  </Card>
  <Card title="Local Transcription" icon="microphone">
    Whisper runs on-device
  </Card>
  <Card title="Simple API" icon="code">
    Connect in minutes
  </Card>
</CardGroup>


## Quick Start

Get transcription working in 2 minutes:

<Steps>
  <Step title="Copy This Code">
    Replace your `ViewController.swift` with:

    ```swift
    import UIKit
    import omi_lib

    class ViewController: UIViewController {

        override func viewDidLoad() {
            super.viewDidLoad()
            self.lookForDevice()
        }

        func lookForDevice() {
            OmiManager.startScan { device, error in
                print("starting scan")
                if let device = device {
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
    }
    ```
  </Step>
  <Step title="Build and Run">
    1. Select your development team
    2. Connect your iPhone via cable (simulators don't support Bluetooth)
    3. Run the project
  </Step>
  <Step title="Test It">
    1. Turn on your Omi device
    2. The app should connect automatically
    3. Speak - you'll see transcription in the Xcode console

    <Note>
    There's no UI in this example - transcription appears in the Xcode logs.
    </Note>

    <img
      src="https://github.com/user-attachments/assets/636b33ac-7ea7-4e1c-b490-8ec99b1feef8"
      alt="Xcode Console Output"
      style={{maxWidth: '600px'}}
    />
  </Step>
</Steps>


## OmiManager Methods

| Method | Description |
|--------|-------------|
| `startScan(callback)` | Start scanning for Omi devices |
| `endScan()` | Stop scanning |
| `connectToDevice(device)` | Connect to a discovered device |
| `connectionUpdated(callback)` | Monitor connection state changes |
| `getLiveTranscription(device, callback)` | Receive real-time transcription |
| `getLiveAudio(device, callback)` | Receive audio file URLs |


## Related

<CardGroup cols={2}>
  <Card title="SDK Overview" icon="cube" href="/doc/developer/sdk/sdk">
    Compare all available SDKs
  </Card>
  <Card title="GitHub Source" icon="github" href="https://github.com/BasedHardware/omi">
    View source code and contribute
  </Card>
</CardGroup>
