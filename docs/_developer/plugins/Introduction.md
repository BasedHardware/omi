---
title: Introduction
layout: default
parent: Plugins
nav_order: 1
---

# FRIEND Plugin Development: Expanding AI Capabilities

Welcome to the FRIEND Plugin ecosystem. Here, developers can extend and enhance the functionality of the FRIEND AI
assistant, creating powerful tools for productivity, analysis, and integration with external services.

## What Are FRIEND Plugins?

FRIEND plugins are modular extensions that augment the core functionality of the AI assistant. They enable:

- Task automation
- Integration with third-party services
- Addition of new features and capabilities

Plugins can transform FRIEND into a specialized tool for various applications, from productivity enhancement to data
analysis and beyond.

## Plugin Types

### 1. Prompt-Based Plugins: Customizing AI Behavior

These plugins modify how FRIEND processes and responds to information:

a) **Chat Prompts**: Alter FRIEND's conversational style and knowledge base. For example, you could create a plugin that
makes FRIEND communicate like a specific expert or professional in a given field.

b) **Memory Prompts**: These plugins analyze conversations and extract specific information based on predefined
criteria. They can be used for summarization, key point extraction, or identifying action items from discussions.

### 2. Integration Plugins: Connecting FRIEND to External Systems

These plugins allow FRIEND to interact with external services and process data in real-time:

a) **Memory Creation Triggers**: Activated when FRIEND creates a new memory. These can be used to:

- Update project management tools with conversation summaries
- Create a personalized social platform that matches you with like-minded individuals based on your conversations and
  interests
- Generate a comprehensive knowledge graph of your interests, experiences, and relationships over time

b) **Real-Time Transcript Processors**: These process conversation transcripts as they occur, enabling:

- Live conversation coaching, providing feedback on communication skills and suggesting improvements in real-time
- Handling trigger phrases like "Hey Friend, remind me to..." to set reminders or "Hey Friend, add to cart..." to update
  your shopping lists
- Performing real-time web searches or fact-checking during conversations
- Analyzing emotional states and providing supportive responses or suggestions
- Integrating with smart home systems to control devices based on conversational cues

## Potential Applications

The FRIEND plugin system opens up a wide range of possibilities:

- A productivity plugin that extracts action items from meetings and adds them to a task management system
- A research assistant that provides real-time fact-checking and source citation
- A personal CRM that analyzes conversations and updates contact information and interaction history
- A data analysis tool that processes conversations about financial topics and provides instant market insights
- A plugin that generates structured data from casual conversations, potentially powering applications like social
  networks or dating apps based on conversational content

## Getting Started

To contribute your plugin to the FRIEND community:

1. Develop your plugin following our [Plugin Development Guide](#).
2. Test your plugin thoroughly using our [Plugin Testing Framework](#).
3. Submit a pull request to
   our [community-plugins.json](https://github.com/BasedHardware/Friend/blob/main/community-plugins.json) file on
   GitHub, appending your plugin details.

For more detailed information, please refer to our guides on [Creating Prompt-Based Plugins](#)
and [Building Integration Plugins](#).

We're excited to see how you'll expand FRIEND's capabilities. Happy developing!