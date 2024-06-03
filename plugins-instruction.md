**Community Plugins format**

To add your plugin to the list, make a pull request to the [community-plugins.json](https://github.com/BasedHardware/Friend/blob/feature-plugins/community-plugins.json) file. Please add your plugin to the end of the list.

Plugins allow to modify prompts that process audio transcriptions. You can create plugins/prompts for every possible usecase, starting from doctor/patient conversation, ending with student's summary of classes

Structure: <br>
- Id: A unique ID for your plugin. Make sure this is the same one you have in your manifest.json.<br>
- Name: The name of your plugin.<br>
- Author: The author's name. <br>
- Description: A short description of what your plugin does.<br>
- Prompt: Describe the prompt of how the transcription should be processes. Each transcription is a conversation between one or multiple users. Conversations are chunked by 30sec+ silence pause<br>


How community plugins are pulled
- You add your plugin to the [list](https://github.com/BasedHardware/Friend/blob/feature-plugins/community-plugins.json) 
- Based Hardware team will read the list of plugins in community-plugins.json and approve it
- The plugin becomes available in the Plugins marketplace of the FRIEND mobile app and users can install it
