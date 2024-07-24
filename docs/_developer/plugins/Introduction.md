---
title: Introduction
layout: default
parent: Plugins
nav_order: 1
---

# Plugins Introduction

Plugins are integrations that allow users to extend the functionality of the FRIEND app. They can be used to automate
tasks, integrate with third-party services, or add new features to the app. Plugins can be triggered by events such as
memory creation or transcript received and can also interact with the app's data by having them as a prompt for the chat
functionality as well as prompts for memory creation.

## Contribution Process

To add your plugin to the community list, create a pull request on
the [community-plugins.json](https://github.com/BasedHardware/Friend/blob/main/community-plugins.json) file on GitHub,
appending your plugin at the end. More details on [Submitting Your Plugin](#submitting-your-plugin).

### Plugin Types

There are 2 types of plugins:

1. **Prompt Based Plugins:** This type of plugin can interact when a memory is created by expanding the summary results,
   and .
2. **Integrations Plugins:** This type of plugin can interact when a transcript is received, and can be used to integrate
   with third-party services.


- [ ] Explain how and when each interacts + examples.
- [ ] Improve details about each type