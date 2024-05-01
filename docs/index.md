---
layout: default
title: Introduction
nav_order: 1
---

# Introduction

Friend is an AI wearable device that records everything you say, giving you proactive feedback and advice. Use these docs to unlock the full potential of Friend and build using the power of recall.

<img src="https://basedhardware.github.io/Friend/images/mainbanner.jpeg" alt="Friend Banner" width="100%">

## Features

- Real-Time AI Audio Processing: Leverage powerful on-device AI capabilities for real-time audio analysis.

- Low-powered Bluetooth: Capture audio for 24h+ on a small button battery

- Open-Source Software: Access and contribute to the pin’s software stack, designed with openness and community collaboration in mind. -Wearable Design: Experience unparalleled convenience with ergonomic and lightweight design, perfect for everyday wear

## How it works

```mermaid
graph TD;
   A[Device] -- Streams Audio --> B[Phone App];
   B -- Transmits --> C[Deepgram];
   C -- Returns Transcript --> D[Phone App];
   D -- Saves Transcript --> E[Phone Storage];

classDef lightMode fill:#FFFFFF, stroke:#333333, color:#333333;
classDef darkMode fill:#333333, stroke:#FFFFFF, color:#FFFFFF;

classDef lightModeLinks stroke:#333333;
classDef darkModeLinks stroke:#FFFFFF;

class A,B,C,D,E lightMode
class A,B,C,D,E darkMode

linkStyle 0 stroke:#FF4136, stroke-width:2px
linkStyle 1 stroke:#1ABC9C, stroke-width:2px
linkStyle 2 stroke:#FFCC00, stroke-width:2px
linkStyle 3 stroke:#2ECC40, stroke-width:2px
```

## Structure

There are 3 different apps in these repositories located in different branches and folders. Our goal is to merge them into one big project.

Folder "AppStandalone": Standalone version of the app that doesn't require any hardware to use it.

Folder "AppWithWearable": Wearable-connected version of the app that requires the "Friend necklace" to use it.

Folder "AppWithWearableReactNative": Wearable-connected version of the app that is built in React native



[Next Step: Getting Started →](https://basedhardware.github.io/Friend/get_started/Setup/){: .btn .btn-purple }