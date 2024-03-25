# Friend: Long-Lasting Open-Source AI Wearable

![IMG_0516](https://github.com/BasedHardware/friend/assets/43514161/f333cecb-cab8-481e-ae9b-37b9b742e2c1)
[![Discord Follow](https://dcbadge.vercel.app/api/server/kEXXsnb5b3?style=flat)](https://discord.gg/kEXXsnb5b3) &ensp;
[![License: GPLv3](https://img.shields.io/badge/license-GPLv3-blue)](https://opensource.org/license/agpl-v3)

Our vision is to make wearable AI accessible to everyone, to use and to build on. Our mission is to provide the tools and support, so that you can focus on what matters.

Be a part of the revolution! **Friend** is here to stay, at the forefront of AI hardware innovation.

<!-- ## Features

- **Real-Time AI Audio Processing**: Leverage powerful on-device AI capabilities for real-time audio analysis.
- **Low-powered Bluetooth**: Capture audio for 24h+ on a small button battery
- **Open-Source Software**: Access and contribute to the pin's software stack, designed with openness and community collaboration in mind.
- **Wearable Design**: Experience unparalleled convenience with ergonomic and lightweight design, perfect for everyday wear. -->

## Structure
There are 2 different apps in these repositories located in different branches. Our goal is to merge them into one big project. 
[Standalone Branch](https://github.com/BasedHardware/friend/tree/standalone): Standalone version of the app that doesn't require any hardware to use it. Try example [here](https://apps.apple.com/us/app/comind-real-world-notetaker/id6474986074) used by thousands of people
[AppWithWearable Branch](https://github.com/BasedHardware/friend/tree/appwithwearable) Wearable-connected version of the app that requires the "Friend necklace" to use it
[Main Branch] Branch that contains firmware for SeeedStudio XIAO NRF52840 Sense Board

## Getting Started 

Follow these steps to get started with your Friend:

Clone the repo ``` git clone https://github.com/BasedHardware/friend.git ```
Install [Flutter](https://docs.flutter.dev/get-started/install/macos/mobile-ios?tab=download) and [CocoaPods](https://guides.cocoapods.org/using/getting-started.html)

iOS: [Install XCode](https://apps.apple.com/us/app/xcode/id497799835?mt=12) then navigate to the iOS folder
Android: Download/install [android Studio ](https://developer.android.com/studio) then navigate to the Android folder

then run ```flutter clean ``` then ``` flutter pub get ``` then ``` pod install ```
When everything is installed, run ```flutter run ```, this should open Xcode and run your app. 

## Contributing
[Join our Discord!](https://discord.gg/kEXXsnb5b3)
We welcome contributions from the community! If you're interested in improving Friend, to learn how you can get involved in Discord!

## Support

For open-source support, please open an issue on GitHub and/or ask in our [Discord Community](https://discord.gg/kEXXsnb5b3). For commercial support, license inquiries, or any other questions, please contact us directly at [team@whomane.com](mailto:team@whomane.com).



## Disclaimer

Please note that the Friend is a prototype project and is provided "as is", without warranty of any kind. Use of the device should comply with all local laws and regulations concerning privacy and data protection.

Thank you for your interest in Friend, the open-source AI wearable. We're excited to see what you'll build with it!

## Licensing

Friend is available under dual licensing options:

1. **GNU General Public License (GPL)**: For open-source projects and community development, Friend is available under the GPL. This strong copyleft license ensures that all modifications and derived works are also open-source, fostering a collaborative development environment.

2. **Commercial License**: For individuals or entities wishing to use Friend in closed-source projects or who require more flexible licensing terms than those offered by the GPL, a commercial license is available. The commercial license permits private modification, use, and distribution, as well as commercial support and warranty.

### Choosing Your License

- If you wish to contribute to or use Friend in open-source projects, you are free to do so under the terms of the GPL, as detailed in the LICENSE file.
- If you require a commercial license for your project or enterprise, please contact us at [team@whomane.com](mailto:team@whomane.com) to discuss your needs and obtain licensing information.
