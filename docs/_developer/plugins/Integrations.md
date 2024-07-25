---
title: Integration Plugins
layout: default
parent: Plugins
nav_order: 3
---

# 🚀 Developing Integration Plugins for FRIEND

Integration plugins allow FRIEND to interact with external services and process data in real-time. This guide will walk
you through creating both Memory Creation Triggers and Real-Time Transcript Processors.

## Types of Integration Plugins

### 1. 👷 Memory Creation Triggers

These plugins are activated when FRIEND creates a new memory, allowing you to process or store the memory data
externally.

[![Memory trigger plugin](https://img.youtube.com/vi/Yv7gP3GZ0ME/0.jpg)](https://youtube.com/shorts/Yv7gP3GZ0ME)

#### Example Use Cases

- Update project management tools with conversation summaries
- Create a personalized social platform based on conversations and interests
- Generate a knowledge graph of interests, experiences, and relationships

### 2. 🏎️ Real-Time Transcript Processors

These plugins process conversation transcripts as they occur, enabling real-time analysis and actions.

[![Real-time processing plugin](https://img.youtube.com/vi/h4ojO3WzkxQ/0.jpg)](https://youtube.com/shorts/h4ojO3WzkxQ)

#### Example Use Cases

- Live conversation coaching and feedback
- Real-time web searches or fact-checking
- Emotional state analysis and supportive responses

## Creating an Integration Plugin

### Step 1: Define Your Plugin 🎯

Decide whether you're creating a Memory Creation Trigger or a Real-Time Transcript Processor, and outline its specific
purpose.

### Step 2: Set Up Your Endpoint 🔗

Create an endpoint that can receive and process the data sent by FRIEND. The data structure will differ based on your
plugin type:

#### For Memory Creation Triggers:

Your endpoint will receive the entire memory object as a JSON payload, with a `uid` as a query parameter. Here's what to
expect:

```json
GET /your-endpoint?uid=user123

{
    "id": 0,
    "created_at": "2024-07-22T23:59:45.910559+00:00",
    "started_at": "2024-07-21T22:34:43.384323+00:00",
    "finished_at": "2024-07-21T22:35:43.384323+00:00",
    "transcript": "Full transcript text...",
    "transcript_segments": [
        {
        "text": "Segment text",
        "speaker": "SPEAKER_00",
        "speakerId": 0,
        "is_user": false,
        "start": 10.0,
        "end": 20.0
        }
      // More segments...
    ],
    "photos": [],
    "structured": {
    "title": "Conversation Title",
    "overview": "Brief overview...",
    "emoji": "🗣️",
    "category": "personal",
    "action_items": [
        {
        "description": "Action item description",
        "completed": false
        }
    ],
    "events": []
    },
    "plugins_response": [
        {
        "plugin_id": "plugin-id",
        "content": "Plugin response content"
        }
    ],
    "discarded": false
}
```

Your plugin should process this entire object and perform any necessary actions based on the full context of the memory.

**For Real-Time Transcript Processors:**

Your endpoint will receive a JSON payload containing the most recently transcribed segments, with both session_id and
uid as query parameters. Here's the structure:

```
GET /your-endpoint?session_id=abc123&uid=user123

[
  {
    "text": "Segment text",
    "speaker": "SPEAKER_00",
    "speakerId": 0,
    "is_user": false,
    "start": 10.0,
    "end": 20.0
  }
  // More recent segments...
]
```

**Key points for Real-Time Transcript Processors:**

1. Segments arrive in multiple calls as the conversation unfolds.
2. Use the session_id to maintain context across calls.
3. Implement smart logic to avoid redundant processing.
4. Consider building a complete conversation context by accumulating segments.
5. Clear processed segments to prevent re-triggering on future calls.

Remember to handle errors gracefully and consider performance, especially for lengthy conversations!


### Step 3: Test Your Plugin 🧪
Time to put your plugin through its paces:

1. Open the FRIEND app on your device.
2. Go to Settings and enable Developer Mode.
3. Navigate to Developer Settings.
4. Set your endpoint URL for either Memory Creation or Transcript Processing.

Your endpoints are now ready to spring into action when events occur!
For Memory Creation Triggers, you can also test without waiting for a new memory:

1. Go to any memory detail view.
2. Click on the top right corner (3 dots menu).
3. In the Developer Tools section, trigger the endpoint call with existing memory data.

Happy plugin crafting! We can't wait to see what you create! 🎉