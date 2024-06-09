<div align="center">

# **Friend**

Meet Friend, the world’s leading open-source AI wearable that revolutionizes how you capture and manage conversations. Simply connect Friend to your mobile device and enjoy automatic, high-quality transcriptions of meetings, chats, and voice memos wherever you are.

![Friend Image](/docs/images/friend_banner.png)

[![Discord Follow](https://dcbadge.vercel.app/api/server/ZutWMTJnwA?style=flat)](https://discord.gg/ZutWMTJnwA) &ensp;&ensp;&ensp;
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)&ensp;&ensp;&ensp;
[![GitHub Repo stars](https://img.shields.io/github/stars/BasedHardware/Friend)](https://github.com/BasedHardware/Friend)

<h3>

[Homepage](https://basedhardware.com/) | [Documentation](https://docs.basedhardware.com/) | [Buy Assembled Device](https://www.kickstarter.com/projects/kodjima333/friend-open-source-ai-wearable-recording-device?ref=7wc2iz)

</h3>

</div>

## Features

- **Real-Time AI Audio Processing**: Leverage powerful on-device AI capabilities for real-time audio analysis.
- **Low-powered Bluetooth**: Capture audio for 24h+ on a small button battery
- **Open-Source Software**: Access and contribute to the pin's software stack, designed with openness and community collaboration in mind.
- **Wearable Design**: Experience unparalleled convenience with ergonomic and lightweight design, perfect for everyday wear.

## Get Started with our Documentation:

- [Introduction](https://docs.basedhardware.com/)
- [App setup](https://docs.basedhardware.com/get_started/Setup/)
- [Buying Guide](https://docs.basedhardware.com/assembly/Buying_Guide/)
- [Build the device](https://docs.basedhardware.com/assembly/Build_the_device/)
- [Install firmware](https://docs.basedhardware.com/assembly/Install_firmware/)

## Contribution:

We welcome contributions from the community! If you are interested in improving Friend, check out our [current tasks](https://github.com/BasedHardware/Friend/issues)

We also want to give back to the community - and therefore, some of the tasks are paid bounties 💰! You can check which ones by the "Paid Bounty" label, [here](https://github.com/BasedHardware/Friend/issues?q=is:open+is:issue+label:%22Paid+Bounty+%F0%9F%92%B0%22)


## How it works

```mermaid
graph TD;
   A[Device] -- Streams Audio --> B[Phone App];
   B -- Transmits --> C[Deepgram];
   C -- Returns Transcript --> D[Phone App];
   D -- Sends Transcript to Plugins Enabled --> G[Community Plugins];
   D -- Saves Original Transcript --> E[Phone Storage];
   G -- Saves Plugin Responses --> E;

classDef lightMode fill:#FFFFFF, stroke:#333333, color:#333333;
classDef darkMode fill:#333333, stroke:#FFFFFF, color:#FFFFFF;

classDef lightModeLinks stroke:#333333;
classDef darkModeLinks stroke:#FFFFFF;

class A,B,C,D,E,G lightMode;
class A,B,C,D,E,G darkMode;

linkStyle 0 stroke:#FF4136, stroke-width:2px;
linkStyle 1 stroke:#1ABC9C, stroke-width:2px;
linkStyle 2 stroke:#0074D9, stroke-width:2px;
linkStyle 3 stroke:#FFCC00, stroke-width:2px;
linkStyle 4 stroke:#2ECC40, stroke-width:2px;
linkStyle 5 stroke:#B10DC9, stroke-width:2px;

```

## Get the software

Get the Android app on [Google Play](https://play.google.com/store/apps/details?id=com.friend.ios)

Download the iOS app in [App Store](https://apps.apple.com/us/app/friend-ai-wearable/id6502156163)

iOS app beta on [TestFlight](https://testflight.apple.com/join/Ie8VQ847)

Latest firmware: [v1.0.2](https://github.com/BasedHardware/Friend/releases/download/v1.0.2-Firmware/friend-firmware.uf2)

Or you can build your own app from the sources in `apps/AppWithWearable` and firmware from `firmware` folders.

[Next Step: Read Getting Started →](https://docs.basedhardware.com/get_started/Setup/)

# Getting Started

Follow these steps to get started with your Friend.

### Install the app

Before starting, make sure you have the following installed:

- Flutter SDK
- Dart SDK
- Xcode (for iOS)
- Android Studio (for Android)
- CocoaPods (for iOS dependencies)

### Setup Instructions

1. **Upgrade Flutter**:
   Before proceeding, make sure your Flutter SDK is up to date:
    ```
    flutter upgrade
    ```

2. **Get Flutter Dependencies**:
   From within `apps/AppWithWearable`, install flutter packages:
    ```
    flutter pub get
    ```

3. **Install iOS Pods**:
   Navigate to the iOS directory and install the CocoaPods dependencies:
    ```
    cd ios
    pod install
    pod repo update
    ```

4. **Environment Configuration**:
   Create `.env` using template `.env.template`
    ```
    cd ..
    cat .env.template > .env
    ```

5. **API Keys**:
   Add your API keys to the `.env` file. (Sentry is not needed)

6. **Run Build Runner**:
   Generate necessary files with Build Runner:
    ```
    dart run build_runner build
    ```

7. **Run the App**:
    - Select your target device in Xcode or Android Studio.
    - Run the app.

[Next Step: Buying Guide →](https://docs.basedhardware.com/assembly/Buying_Guide/)

## More links:

- [Contributing](https://docs.basedhardware.com/info/Contribution/)
- [Roadmap and Tasks](https://github.com/BasedHardware/Friend/issues)
- [Support](https://docs.basedhardware.com/info/Support/)
- [Our bluetooth Protocol Standard](https://docs.basedhardware.com/developer/Protocol/)
- [Plugins](https://docs.basedhardware.com/developer/Plugins/)

## Made by the Community, with -❤️-:

<a href="https://github.com/BasedHardware/Friend/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=BasedHardware/Friend" />
</a>

## Licensing

Friend is available under MIT License
