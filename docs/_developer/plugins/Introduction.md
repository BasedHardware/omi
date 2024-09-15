---
title: Introduction
layout: default
parent: Plugins
nav_order: 1
---

# FRIEND Plugin Development: Expanding AI Capabilities

As a developer, you can create plugin for Friend app, letting other people to use your plugins and earn in the future.

## What Are FRIEND Plugins?

FRIEND plugins are modular extensions that augment the core functionality of the app. They can modify app's
behavior, analyze conversations, and connect with external services.

Plugins enable:

- Customized AI personalities and knowledge bases
- Extraction of specific information from conversations
- Task automation and integration with third-party services
- Real-time conversation analysis and insights

[//]: # (With plugins, FRIEND can be transformed into specialized tools such as:)

[//]: # (- A personal productivity coach that extracts action items and updates task management systems)

[//]: # (- An expert in any field, providing specialized knowledge and advice)

[//]: # (- A real-time language translator and cultural advisor)

[//]: # (- A personal CRM that analyzes conversations and maintains relationship histories)

[//]: # (- A health and fitness tracker that interprets discussions about diet and exercise)

Plugins allow developers to tap into FRIEND's conversational abilities and combine them with external data and services,
opening up a world of possibilities for AI-enhanced applications.

## Plugin Types

### 1. Prompt-Based Plugins: Customizing AI Behavior

These plugins modify how FRIEND processes and responds to information:

| Type                  | Description                                                                          | Example                                                                                                | Example Video                                                                                            |
|-----------------------|--------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------|
| **💬 Chat Prompts**   | Alter FRIEND's conversational style and knowledge base.                              | Create a plugin that makes FRIEND communicate like a specific expert or professional in a given field. | [![Chat plugin](https://img.youtube.com/vi/k1XhccNDT94/0.jpg)](https://youtube.com/shorts/k1XhccNDT94)   |
| **🧠 Memory Prompts** | Analyze conversations and extract specific information based on predefined criteria. | Use for summarization, key point extraction, or identifying action items from discussions.             | [![Memory plugin](https://img.youtube.com/vi/Y3ehX_ueQmE/0.jpg)](https://youtube.com/shorts/Y3ehX_ueQmE) |

### 2. Integration Plugins: Connecting FRIEND to External Systems

These plugins allow FRIEND to interact with external services and process data in real-time:

| Plugin Type                                                             | Description                                    | Use Cases                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Example Video                                                                                                    |
|-------------------------------------------------------------------------|------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| **👷 Memory Creation Triggers**                                         | Activated when FRIEND creates a new memory     | - Update project management tools with conversation summaries<br>- Create a personalized social platform that matches you with like-minded individuals based on your conversations and interests<br>- Generate a comprehensive knowledge graph of your interests, experiences, and relationships over time                                                                                                                                                                                                                | [![Memory trigger plugin](https://img.youtube.com/vi/Yv7gP3GZ0ME/0.jpg)](https://youtube.com/shorts/Yv7gP3GZ0ME) |
| **🏎️ Real-Time Transcript Processors `(@DEPRECATED / NOT READY YET)`** | Process conversation transcripts as they occur | - Live conversation coaching, providing feedback on communication skills and suggesting improvements in real-time<br>- Handling trigger phrases like "Hey Friend, remind me to..." to set reminders or "Hey Friend, add to cart..." to update your shopping lists<br>- Performing real-time web searches or fact-checking during conversations<br>- Analyzing emotional states and providing supportive responses or suggestions<br>- Integrating with smart home systems to control devices based on conversational cues | [![Memory trigger plugin](https://img.youtube.com/vi/h4ojO3WzkxQ/0.jpg)](https://youtube.com/shorts/h4ojO3WzkxQ) |

## Potential Applications

The FRIEND plugin system opens up a wide range of possibilities:

- A productivity plugin that extracts action items from meetings and adds them to a task management system
- A research assistant that provides real-time fact-checking and source citation
- A personal CRM that analyzes conversations and updates contact information and interaction history
- A data analysis tool that processes conversations about financial topics and provides instant market insights
- A plugin that generates structured data from casual conversations, potentially powering applications like social
  networks or dating apps based on conversational content

## Getting Started

To contribute your plugin to the FRIEND community, follow these steps based on the type of plugin you want to create:

1. Read our [Prompt-Based Plugin Guide](https://docs.omi.me/developer/plugins/PromptBased/) or check
   our [Integration Plugin Guide](https://docs.omi.me/developer/plugins/Integrations/) to
   understand the process.
2. Develop and test your plugin following the guidelines provided.
3. Submit a pull request to
   our [community-plugins.json](https://github.com/BasedHardware/Omi/blob/main/community-plugins.json) file on
   GitHub, appending your plugin details.

We're excited to see how you'll expand FRIEND's capabilities. Happy developing!
