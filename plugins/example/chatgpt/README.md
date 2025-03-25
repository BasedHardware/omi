# OMI ChatGPT Integration

This plugin enables integration between OMI conversations and ChatGPT custom GPTs using OpenAI's Actions feature with OAuth authentication.

## Features

- Receive and store conversation data from OMI
- Provide OAuth authentication for secure access to OMI data
- Expose API endpoints for ChatGPT Actions to access OMI conversation data
- Initially uses in-memory storage with plans to use Supabase for persistence

## Setup Instructions

### 1. Setting Up Your Environment

1. Copy the `.env.template` file to create a `.env` file:

   ```bash
   cp .env.template .env
   ```

2. (Optional) Edit the `.env` file with your credentials:
   ```
   # Generate your own client ID and secret or let the server generate them for you
   OPENAI_CLIENT_ID=your_self_generated_client_id
   OPENAI_CLIENT_SECRET=your_self_generated_client_secret
   ```

   Note: If you don't set these values, the server will automatically generate random values when started.

### 2. Starting the Server

Run the server using the provided script:

```bash
chmod +x run.sh  # Make the script executable (first time only)
./run.sh
```

This will start a FastAPI server on port 8000, and it will display your OAuth credentials:

```
OAuth Configuration for ChatGPT Actions:
Authorization URL: http://localhost:8000/chatgpt/oauth/authorize
Token URL: http://localhost:8000/chatgpt/oauth/token
Client ID: generated_client_id
Scope: read:memories
```

Copy these values for use in your ChatGPT Action.

### 3. Setting Up Your ChatGPT Action

In the OpenAI developer portal, create a new GPT Action with OAuth authentication:

1. Select "OAuth" as the Authentication Type
2. Fill in the fields:
   - **Client ID**: Use the generated Client ID from your server
   - **Client Secret**: Use the generated Client Secret from your server
   - **Authorization URL**: Your server's authorization URL (e.g., `http://localhost:8000/chatgpt/oauth/authorize`)
   - **Token URL**: Your server's token URL (e.g., `http://localhost:8000/chatgpt/oauth/token`)
   - **Scope**: `read:memories`
   - **Token Exchange Method**: Default (POST request)

### 4. Setting Up the OpenAPI Schema for Your Action

Use the following OpenAPI schema in your ChatGPT Action:

```yaml
openapi: 3.0.0
info:
  title: OMI Conversations API
  description: Access your OMI conversations and transcripts
  version: 1.0.0
servers:
  - url: http://localhost:8000
paths:
  /api/conversations:
    get:
      operationId: getConversations
      summary: Get a list of all OMI conversations
      security:
        - bearerAuth: []
      responses:
        '200':
          description: List of conversations
          content:
            application/json:
              schema:
                type: object
                properties:
                  conversations:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                        title:
                          type: string
                        created_at:
                          type: string
                        category:
                          type: string
                        overview:
                          type: string
  /api/conversations/{conversation_id}:
    get:
      operationId: getConversation
      summary: Get details of a specific conversation
      security:
        - bearerAuth: []
      parameters:
        - name: conversation_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Conversation details
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  created_at:
                    type: string
                  started_at:
                    type: string
                    nullable: true
                  finished_at:
                    type: string
                    nullable: true
                  transcript:
                    type: string
                  structured:
                    type: object
                    properties:
                      title:
                        type: string
                      overview:
                        type: string
                      emoji:
                        type: string
                      category:
                        type: string
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
```

### 5. Testing the Integration

For local development, you can use ngrok to expose your server to the internet:

```bash
ngrok http 8000
```

Use the ngrok URL in your ChatGPT Action configuration.

### 6. Using the Integration

When using your ChatGPT, it will:

1. Request the user to authenticate with OMI when they try to access conversation data
2. Guide them through the OAuth flow
3. Store the tokens for future requests
4. Allow access to conversation data via the API endpoints

## Production Deployment

For production deployment:

1. Deploy your FastAPI application to a server with a public HTTPS URL
2. Update the OAuth URLs and server URL in your ChatGPT Action configuration
3. Consider implementing a proper database for storing tokens and conversation data
4. Add more robust error handling and security measures

## Webhook Integration with OMI

To receive memory data from OMI, use the following webhook endpoint:

```
https://your-server-url.com/chatgpt/webhook/memory
```

### Setting up the webhook in OMI:

1. Open the OMI app on your device
2. Go to Settings and enable Developer Mode
3. Navigate to Developer Settings
4. For Memory Creation Triggers:
   - Set your endpoint URL to `https://your-server-url.com/chatgpt/webhook/memory` in the "Memory Creation Webhook" field

The webhook endpoint:
- Logs the received data to the console for debugging
- Stores valid memory data for later retrieval via the API
- Accepts the `uid` query parameter to associate memories with specific users

### Example curl command to test the webhook:

```bash
curl -X POST "https://your-server-url.com/chatgpt/webhook/memory?uid=test_user" \
  -H "Content-Type: application/json" \
  -d '{
    "created_at": "2024-07-22T23:59:45.910559+00:00",
    "started_at": "2024-07-21T22:34:43.384323+00:00",
    "finished_at": "2024-07-21T22:35:43.384323+00:00",
    "transcript_segments": [
      {
        "text": "Test segment text",
        "speaker": "SPEAKER_00",
        "speakerId": 0,
        "is_user": false,
        "start": 10.0,
        "end": 20.0
      }
    ],
    "photos": [],
    "structured": {
      "title": "Test Conversation",
      "overview": "This is a test overview",
      "emoji": "🗣️",
      "category": "personal"
    },
    "plugins_results": [
      {
        "plugin_id": "test-app-id",
        "content": "Test app response"
      }
    ],
    "discarded": false
  }' 