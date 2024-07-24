---
title: Integrations
layout: default
parent: Plugins
nav_order: 3
---


# Building Integrations Plugins

This guide explains how to create plugins that can work as a standalone app on top of FRIEND infrastructure. There are
three main ways to integrate with the app:

1. On Memory Created plugins
2. On Transcript Received plugins

## Table of Contents

1. [Plugin Types](#plugin-types)
2. [Plugin Structure](#plugin-structure)
3. [Setting Up the Environment](#setting-up-the-environment)
4. [Creating a Plugin](#creating-a-plugin)
5. [On Memory Created Plugin Example](#on-memory-created-plugin-example)
6. [On Transcript Received Plugin Example](#on-transcript-received-plugin-example)
7. [Submitting Your Plugin](#submitting-your-plugin)

## Plugin Types

### 1. On Memory Created Plugins

These plugins are triggered when a new memory is created, similar to webhooks. However, these can be installed by all
users.

### 2. On Transcript Received Plugins

These plugins listen for conversation transcripts and are processed every 30 seconds. The current set of new transcripts
is sent to the plugin for processing.

## Plugin Structure

Plugins are defined using a JSON structure. Here's an example:

```json
{
  "id": "notion-conversations-crm",
  "name": "Notion Conversations CRM",
  "author": "@josancamon19",
  "description": "Stores all your conversations into a notion database",
  "image": "/assets/plugin_images/notion-crm.png",
  "prompt": "",
  "memories": false,
  "chat": false,
  "capabilities": [
    "external_integration"
  ],
  "external_integration": {
    "triggers_on": "memory_creation",
    "webhook_url": "https://josancamon19--plugins-examples-plugins-app.modal.run/notion-crm",
    "setup_instructions_file_path": "/assets/external_plugins_instructions/notion-conversations-crm.md"
  }
}
```

## Creating a Plugin

## On Memory Created Plugin Example

Here's an example of an On Memory Created plugin (Notion CRM):

```python
@app.post('/notion-crm')
def notion_crm(memory: Memory, uid: str):
    notion_api_key = get_notion_crm_api_key(uid)
    if not notion_api_key:
        return {'message': 'Your Notion CRM plugin is not enabled. Please enable it in the settings.'}
    store_memoy_in_db(notion_api_key, get_notion_database_id(uid), memory)
    return {}
```

## On Transcript Received Plugin Example

Here's an example of an On Transcript Received plugin (News Checker):

```python
@app.post('/news-checker')
def news_checker_endpoint(uid: str, data: dict):
    session_id = data['session_id']
    segments = data['segments']
    return {'message': news_checker(segments)}
```

## Submitting Your Plugin

To submit your plugin for users to see on their available plugins list, create a Pull Request with the following JSON
structure:

`triggers_on` param could be `memory_creation` or `transcript_processed`

```json
{
  "id": "your-plugin-id",
  "name": "Your Plugin Name",
  "author": "@your-username",
  "description": "A brief description of your plugin",
  "image": "/assets/plugin_images/your-plugin-image.png",
  "prompt": "",
  "memories": false,
  "chat": false,
  "capabilities": [
    "external_integration"
  ],
  "external_integration": {
    "triggers_on": "memory_creation",
    "webhook_url": "https://your-plugin-url.com/endpoint",
    "setup_instructions_file_path": "/assets/external_plugins_instructions/your-plugin-instructions.md"
  }
}
```

### Models

Structure of plugin data received.

```python
# transcript_processed plugin
class TranscriptSegment(BaseModel):
    text: str
    speaker: str
    speaker_id: int
    is_user: bool
    start: float
    end: float


# memory_created plugin
class Memory(BaseModel):
    createdAt: datetime
    startedAt: Optional[datetime] = None
    finishedAt: Optional[datetime] = None
    transcript: str = ''
    transcriptSegments: List[TranscriptSegment] = []
    photos: Optional[List[MemoryPhoto]] = []
    recordingFilePath: Optional[str] = None
    recordingFileBase64: Optional[str] = None
    structured: Structured
    pluginsResponse: List[PluginResponse] = []
    discarded: bool

```

### Submission Details

1. Fork the repository.
2. Create a feature branch.
3. Add your plugin entry to `community-plugins.json`.
4. Create an image for your plugin and place it in the `/assets/plugin_images` directory with the
   name `{plugin_id}.png`.
5. Commit with a message like "Add [PluginName] to community plugins."
6. Open a pull request with a clear plugin description.

Plugin submissions will be reviewed for integration into the main repository.

## How Community Plugins are Pulled

1. **Adding Your Plugin**: Submit your plugin by adding it to the `community-plugins.json` list via a pull request.
2. **Approval**: The Based Hardware team will review your plugin entry for completeness, coherence, and functionality.
   We will also review the included image for appropriateness and adherence to the specified format and size.
3. **Marketplace Availability**: Once approved, your plugin will be listed in the FRIEND mobile app's Plugins
   marketplace, where users can easily browse and install it. The provided image will be displayed alongside your
   plugin's name and description.
