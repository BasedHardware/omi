**Community Plugins format**

To add your plugin to the list, make a pull request to the [community-plugins.json](https://github.com/BasedHardware/Friend/blob/feature-plugins/community-plugins.json) file. Please add your plugin to the end of the list.

Plugins allow to modify prompts that process audio transcriptions. You can create plugins/prompts for every possible usecase, starting from doctor/patient conversation, ending with student's summary of classes

Structure: 
id: A unique ID for your plugin. Make sure this is the same one you have in your manifest.json.
name: The name of your plugin.
author: The author's name.
description: A short description of what your plugin does.
prompt: Describe the prompt of how the transcription should be processes. Each transcription is a conversation between one or multiple users. Conversations are chunked by 30sec+ silence pause
