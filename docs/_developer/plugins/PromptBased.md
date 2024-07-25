---
title: Prompt-Based Plugins
layout: default
parent: Plugins
nav_order: 2
---

# Developing Prompt-Based Plugins for FRIEND

Prompt-based plugins allow you to customize FRIEND's behavior and enhance its ability to process information. This guide
will walk you through creating both Chat Prompts and Memory Prompts.

## Types of Prompt-Based Plugins

### 1. 💬 Chat Prompts

Chat prompts alter FRIEND's conversational style and knowledge base. They allow you to create specialized versions of
FRIEND for different contexts or expertise areas.

[![Chat plugin](https://img.youtube.com/vi/k1XhccNDT94/0.jpg)](https://youtube.com/shorts/k1XhccNDT94)

#### Example Use Case

Create a plugin that makes FRIEND communicate like a specific expert or professional in a given field, such as a
historian, scientist, or creative writer.

### 2. 🧠 Memory Prompts

Memory prompts analyze conversations and extract specific information based on predefined criteria. They're useful for
summarization, key point extraction, or identifying action items from discussions.

[![Memory plugin](https://img.youtube.com/vi/Y3ehX_ueQmE/0.jpg)](https://youtube.com/shorts/Y3ehX_ueQmE)

#### Example Use Case

Develop a plugin that extracts action items from a meeting transcript and compiles them into a to-do list.

Note: It's possible to create plugins that combine both chat and memory capabilities for more comprehensive
functionality.

## Creating a Prompt-Based Plugin

### Step 1: Define Your Plugin

Decide whether you're creating a Chat Prompt, a Memory Prompt, or a combination of both, and outline its specific
purpose.

### Step 2: Write Your Prompt

Craft your prompt carefully. For Chat Prompts, focus on defining the personality and knowledge base. For Memory Prompts,
clearly specify the information to be extracted and how it should be formatted.

### Step 3: Test Your Plugin

Before submitting, it's crucial to test your plugin to ensure it behaves as expected.

#### For Memory Prompts:

1. Download the FRIEND app on your device.
2. Enable developer settings in the app.
3. Open a memory within the app.
4. Click in the top right corner (3 dots menu).
5. In the developer tools section, you can run your prompt to test its functionality.

[![Testing Prompts In-app](https://img.youtube.com/vi/MODjSoTMAh0/0.jpg)](https://youtube.com/shorts/MODjSoTMAh0)

#### For Chat Prompts:

Currently, there isn't an easy way to test chat prompts directly within the app. We're working on improving this
process. In the meantime, you can use your best judgment and thorough proofreading to ensure your chat prompt will
produce the desired results.

### Step 4: Prepare Your Plugin for Submission

Once you're satisfied with your plugin's performance, you'll need to create a JSON object that defines your plugin for
submission. Here's a template:

```json
{
  "id": "your-plugin-id",
  "name": "Your Plugin Name",
  "author": "Your Name",
  "description": "A brief description of what your plugin does",
  "image": "/plugins/logos/your-plugin-logo.jpg",
  "capabilities": [
    "chat"
  ],
  // or ["memories"] or ["chat", "memories"]
  "chat_prompt": "Your chat prompt here",
  // for Chat Prompts
  "memory_prompt": "Your memory prompt here",
  // for Memory Prompts
  "deleted": false
}
```

### Step 5: Submit Your Plugin

To submit your plugin to the FRIEND community:

1. Fork the [FRIEND GitHub repository](https://github.com/BasedHardware/Friend).
2. Locate the `community-plugins.json` file in the repository.
3. Add your plugin's JSON object to the end of the array in this file.
4. Double-check the formatting of your JSON
   using [JSON Formatter & Validator](https://jsonformatter.curiousconcept.com/) to ensure it's correctly formatted.
5. Commit your changes and create a pull request to the main FRIEND repository.

Your pull request should only contain the addition of your plugin's JSON to the `community-plugins.json` file. Once
approved, your plugin will become available to the FRIEND community.

Note: Ensure your plugin adheres to our community guidelines and doesn't contain any sensitive or private information
before submitting.

## Guidelines 📜

While we encourage creativity, please keep these light guidelines in mind:

1. 🤝 **Respect for All**: Avoid content promoting hate or discrimination.

2. 🍭 **All Ages Welcome**: Consider a general audience when creating plugins.

3. 🔍 **Strive for Accuracy**: If providing facts, aim for correctness.

4. 🔒 **Privacy First**: Respect user data and obtain clear consent.

5. ⚖️ **Keep it Legal**: No facilitating illegal activities, please!

6. 🌟 **Community-Driven**: Let users decide what's valuable through their choices.

Remember, these are broad guidelines to allow for creativity. The FRIEND community will shape the plugin ecosystem
through their usage and feedback. When in doubt, ask the community! Let's build together! 🚀