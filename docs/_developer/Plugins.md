---
layout: default
title: Community Plugins
nav_order: 1
---

# Community Plugins

Community Plugins allow modification of prompts that process audio transcriptions into structured data for a multitude of use cases.

## Contribution Process

To add your plugin to the community list, create a pull request on the [community-plugins.json](https://github.com/BasedHardware/Friend/blob/main/community-plugins.json) file on GitHub, appending your plugin at the end.

### Plugin Structure

- `id`: Unique identifier for your plugin, aligned with your manifest.json
- `name`: Descriptive name of your plugin
- `author`: Name of the plugin creator
- `description`: Short summary of what your plugin achieves
- `prompt`: Instructions on processing the transcription, starting with "You will be given a conversation."
- `image`: URL or path to an image that represents your plugin. The image should be named `{plugin_id}.png` and placed in the `/assets/plugin_images` directory. Images should be in PNG format with a recommended size of 300x300 pixels. You can create the image using AI tools like DALL-E, Midjourney, or design it yourself.

#### Good Prompt Example

```json
{
    "id": "thoughtful-therapy-notes",
    "name": "Thoughtful Therapy Notes",
    "author": "John",
    "description": "Transform therapy conversations into structured SOAP notes.",
    "prompt": "You will be given a conversation between a therapist and a patient. Use this information to create detailed session notes by identifying presenting problems, therapeutic interventions, and patient progress. Structure your notes according to the SOAP format without prompting further input. Respect patient confidentiality, and clearly denote any missing information as 'Not Mentioned'.",
    "image": "/assets/plugin_images/thoughtful-therapy-notes.png"
}
```

This prompt is considered good because it is clear, specifies the formatting structure, outlines how to handle missing information, and emphasizes confidentiality. It does not anticipate any response or interaction.

#### Bad Prompt Example

```json
{
    "id": "generic-mentor-guide",
    "name": "Generic Mentor Guide",
    "author": "John",
    "description": "Offers guidance on business issues.",
    "prompt": "You are a mentor. Give good advice. Ask questions if needed.",
    "image": "/assets/plugin_images/generic-mentor-guide.png"
}
```

This prompt falls short as it's too vague, doesn't specify the structure or formatting of the advice, implies the possibility of an interactive exchange which isn't possible, and lacks instructions on handling missing details.

### Submission Details

1. Fork the repository.
2. Create a feature branch.
3. Add your plugin entry to `community-plugins.json`.
4. Create an image for your plugin and place it in the `/assets/plugin_images` directory with the name `{plugin_id}.png`.
5. Commit with a message like "Add [PluginName] to community plugins."
6. Open a pull request with a clear plugin description.

Plugin submissions will be reviewed for integration into the main repository.

## How Community Plugins are Pulled

1. **Adding Your Plugin**: Submit your plugin by adding it to the `community-plugins.json` list via a pull request.
2. **Approval**: The Based Hardware team will review your plugin entry for completeness, coherence, and functionality. We will also review the included image for appropriateness and adherence to the specified format and size.
3. **Marketplace Availability**: Once approved, your plugin will be listed in the FRIEND mobile app's Plugins marketplace, where users can easily browse and install it. The provided image will be displayed alongside your plugin's name and description.