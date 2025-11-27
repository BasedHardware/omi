<div align="center">

# **omi**

Meet Omi, the world’s leading open-source AI wearable that captures conversations, gives summaries, action items and does actions for you. Simply connect Omi to your mobile device and enjoy automatic, high-quality
transcriptions of meetings, chats, and voice memos wherever you are.

<p align="center">
  <img src="https://github.com/user-attachments/assets/834d3fdb-31b5-4f22-ae35-da3d2b9a8f59" alt="Omi" width="49%" />
  <img src="https://github.com/user-attachments/assets/fdad4226-e5ce-4c55-b547-9101edfa3203" alt="Image" width="49%" />

</p>

![CleanShot 2025-02-08 at 18 22 23](https://github.com/user-attachments/assets/7a658366-9e02-4057-bde5-a510e1f0217a)

[![Discord Follow](https://img.shields.io/discord/1192313062041067520?label=Discord)](http://discord.omi.me) &ensp;&ensp;&ensp;
[![Twitter Follow](https://img.shields.io/twitter/follow/kodjima33)](https://x.com/kodjima33) &ensp;&ensp;&ensp;
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)&ensp;&ensp;&ensp;
[![GitHub Repo stars](https://img.shields.io/github/stars/BasedHardware/Omi)](https://github.com/BasedHardware/Omi)

<h3>

[Site](https://omi.me/) |   [Download](https://omi.me/download)   | [Docs](https://docs.omi.me/) | [Buy omi Dev Kit](https://www.omi.me/products/omi-dev-kit-2) | [Buy Omi Glass Dev Kit](https://www.omi.me/glass)

</h3>

</div>

[//]: # "## Features"
[//]: #
[//]: # "- **Real-Time AI Audio Processing**: Leverage powerful on-device AI capabilities for real-time audio analysis."
[//]: # "- **Low-powered Bluetooth**: Capture audio for 24h+ on a small button battery"
[//]: # "- **Open-Source Software**: Access and contribute to the pin's software stack, designed with openness and community collaboration in mind."
[//]: # "- **Wearable Design**: Experience unparalleled convenience with ergonomic and lightweight design, perfect for everyday wear."

## 🚀 Quick Start for Developers (2 min)

Get the omi app running locally:

```bash
git clone https://github.com/BasedHardware/omi.git
cd omi/app

bash setup.sh ios     # android, macos
```

## Create your own App (1 min)

Download omi App

[<img src='https://upload.wikimedia.org/wikipedia/commons/7/78/Google_Play_Store_badge_EN.svg' alt='Get it on Google Play' height="50px" width="180px">](https://play.google.com/store/apps/details?id=com.friend.ios)
[<img src='https://upload.wikimedia.org/wikipedia/commons/3/3c/Download_on_the_App_Store_Badge.svg' alt="Download on the App Store" height="50px" width="180px">](https://apps.apple.com/us/app/friend-ai-wearable/id6502156163)
[<img src='https://github.com/user-attachments/assets/59c47ec7-3da0-47d7-be2f-7467e4189499' alt="Download MacOS app" height="50px" width="180px">](https://apps.apple.com/us/app/omi-ai-smart-meeting-notes/id6502156163)

Create webhook using [webhook.site](https://webhook.site) and copy this url

<img src="https://github.com/user-attachments/assets/083a6ec4-4694-4c7a-843a-4a1a0c254453" width="500">

In omi App:

| Explore => Create an App                                                                                | Select Capability                                                                                       | Paste Webhook URL                                                                                         | Install App                                                                                             |
| ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| <img src="https://github.com/user-attachments/assets/31809b81-7de2-4381-b5fc-5c9714972211" width="200"> | <img src="https://github.com/user-attachments/assets/59cfbe8e-7e3b-437f-81f7-25eb50ccdd7d" width="200"> | <img src="https://github.com/user-attachments/assets/3d864ee8-555f-4ded-b4db-87ff78128323" width = "200"> | <img src="https://github.com/user-attachments/assets/58cf6da6-e245-415e-92e7-dc1f46583cfc" width="200"> |

Start speaking, you'll see Real-time transcript on [webhook.site ](https://webhook.site).

## In this repo:

- [omi device](omi) - nRF chips, zephyr, c/c++
- [omi glass](omiglass) esp32-s3, c/c++
- [omi app](app) - flutter
- [omi backend](backend) - python, fastapi, firebase, pinecone, redis, deepgram, speechmatic, soniox, openai-compatible apis, langchain, silero vad
- [SDKs](sdks) - react native, swift, python
- [ai personas (web)](web/personas-open-source) - nextjs

## Documentation:

- [Introduction](https://docs.omi.me/)
- [omi App setup](https://docs.omi.me/doc/developer/AppSetup)
- [Buying Guide](https://docs.omi.me/doc/assembly/Buying_Guide/)
- [Build the device](https://docs.omi.me/doc/assembly/Build_the_device/)
- [Install firmware](https://docs.omi.me/doc/get_started/Flash_device/)
- [Create your own app in 1 minute](https://docs.omi.me/doc/developer/apps/Introduction).
- [Integrate your own wearable with omi](https://docs.omi.me/doc/integrations)

## Contributions

- Check out our [contributions guide](https://docs.omi.me/doc/developer/Contribution/).
- Earn from contributing! Check the [paid bounties 🤑](https://omi.me/bounties).
- Check out the [current issues](https://github.com/BasedHardware/Omi/issues).
- Join the [Discord](http://discord.omi.me).
- Build your own [Plugins/Integrations](https://docs.omi.me/doc/developer/apps/Introduction).

[//]: # "## More links:"
[//]: #
[//]: # "- [Contributing](https://docs.omi.me/doc/developer/Contribution/)"
[//]: # "- [Support](https://docs.omi.me/doc/info/Support/)"
[//]: # "- [BLE Protocol](https://docs.omi.me/doc/developer/Protocol/)"
[//]: # "- [Plugins](https://docs.omi.me/doc/developer/Plugins/)"

## Licensing

Omi is available under <a href="https://github.com/BasedHardware/omi/blob/main/LICENSE">MIT License</a>
