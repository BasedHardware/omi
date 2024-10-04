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

### 2. 🏎️ Real-Time Transcript Processors (@DEPRECATED / NOT READY YET)

These plugins process conversation transcripts as they occur, enabling real-time analysis and actions.

[![Memory trigger plugin](https://img.youtube.com/vi/h4ojO3WzkxQ/0.jpg)](https://youtube.com/shorts/h4ojO3WzkxQ)

#### Example Use Cases

- Live conversation coaching and feedback
- Real-time web searches or fact-checking
- Emotional state analysis and supportive responses

## Creating an Integration Plugin

### Step 1: Define Your Plugin 🎯

Decide whether you're creating a Memory Creation Trigger or a Real-Time Transcript Processor, and outline its specific
purpose.

### Step 2: Set Up Your Endpoint 🔗

Create an endpoint (webhook) that can receive and process the data sent by FRIEND. You can [create a test webhook](https://webhook-test.com/). The data structure will differ based on your
plugin type:

#### For Memory Creation Triggers:

Your endpoint will receive the entire memory object as a JSON payload, with a `uid` as a query parameter. Here's what to
expect:

`POST /your-endpoint?uid=user123`

```json

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

> Check the [Notion CRM Python Example](https://github.com/BasedHardware/Omi/blob/bab12a678f3cfe43ab1a7aba62645222de4378fb/plugins/example/main.py#L85)
> and it's respective JSON format [here](https://github.com/BasedHardware/Omi/blob/bab12a678f3cfe43ab1a7aba62645222de4378fb/community-plugins.json#L359).

**For Real-Time Transcript Processors:**

Your endpoint will receive a JSON payload containing the most recently transcribed segments, with both session_id and
uid as query parameters. Here's the structure:

`POST /your-endpoint?session_id=abc123&uid=user123`

```json
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

> Check the Realtime News checker [Python Example](https://github.com/BasedHardware/Omi/blob/bab12a678f3cfe43ab1a7aba62645222de4378fb/plugins/example/main.py#L100)
> and it's respective JSON format [here](https://github.com/BasedHardware/Omi/blob/bab12a678f3cfe43ab1a7aba62645222de4378fb/community-plugins.json#L379).

### Step 3: Test Your Plugin 🧪

Time to put your plugin through its paces! Follow these steps to test both types of integrations:

1. Open the FRIEND app on your device.
2. Go to Settings and enable Developer Mode.
3. Navigate to Developer Settings.

#### For Memory Creation Triggers:

4. Set your endpoint URL in the "Memory Creation Webhook" field. If you don't have an endpoint yet, [create a test webhook](https://webhook-test.com/)
5. To test without creating a new memory:
    - Go to any memory detail view.
    - Click on the top right corner (3 dots menu).
    - In the Developer Tools section, trigger the endpoint call with existing memory data.

[![Memory trigger plugin](https://img.youtube.com/vi/dYVSbEpoV0U/0.jpg)](https://youtube.com/shorts/dYVSbEpoV0U)

#### For Real-Time Transcript Processors:

4. Set your endpoint URL in the "Real-Time Transcript Webhook" field.
5. Start speaking to your device - your endpoint will receive real-time updates as you speak.

[![Memory trigger plugin](https://img.youtube.com/vi/CHz9JnOGlTQ/0.jpg)](https://youtube.com/shorts/CHz9JnOGlTQ)

Your endpoints are now ready to spring into action!

For **Memory Creation Triggers**, you can test with existing memories or wait for new ones to be created.

For **Real-Time Processors**, simply start a conversation with FRIEND to see your plugin in action.

Happy plugin crafting! We can't wait to see what you create! 🎉

### Step 4: Prepare Your Plugin for Submission

Create a JSON object defining your plugin:

```json
{
  "id": "your-plugin-id",
  "name": "Your Plugin Name",
  "author": "Your Name",
  "description": "Brief description of your plugin",
  "image": "/plugins/logos/your-plugin-logo.jpg",
  "capabilities": [
    "external_integration"
  ],
  "external_integration": {
    // "memory_creation" | "transcript_processed"
    "triggers_on": "memory_creation",
    // a POST request with the memory object will be sent here as a JSON payload
    "webhook_url": "https://your-endpoint-url.com",
    // GET endpoint, that returns {'is_setup_completed': boolean} (Optional) if your plugin doesn't require setup, set to null.
    "setup_completed_url": "https://your-setup-completion-url.com",
    // Include a Readme with more details about your plugin in the PR
    "setup_instructions_file_path": "/plugins/instructions/your-plugin/README.md"
  },
  "deleted": false
}
```

### Integration Instructions Documentation

Create a markdown file at `setup_instructions_file_path` with:

1. Step-by-step setup guide
2. Screenshots (if applicable)
3. Authentication steps (if required)
4. Troubleshooting tips

Example structure:

```markdown
# Setting Up [Your Plugin Name]

1. [First step]
   ![Step 1](assets/step_1.png)

2. [Second step]
   ![Step 2](assets/step_2.png)

## Authentication (if required)

If your plugin requires user-specific authentication (e.g., connecting to a user's Notion table):

1. In your authentication flow, use the `uid` query parameter we append this as query param to all your links in your
   README, so you can map user credentials.
2. [Authentication steps]
3. After successful authentication, return `{"is_setup_completed": true}` from your `setup_completed_url`.

If your plugin doesn't require user authentication (e.g., it's a purely LLM-based service), you can skip this section.

## Troubleshooting

[Common issues and solutions]

---

> Experimental feature. Feedback: [your email]
```

**Notes:**

- Authentication is not needed for all plugins. Include only if your plugin requires user-specific setup or credentials.
- For plugins without authentication, users can simply enable the plugin without additional steps.
- All your README links, when the user opens them, we'll append a `uid` query parameter to it, which you can use to
  associate setup or credentials with specific users.
