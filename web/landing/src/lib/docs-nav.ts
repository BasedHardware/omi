export interface DocPage {
  title: string;
  slug: string;
  description?: string;
  content?: string;
}

export interface NavGroup {
  title: string;
  items: (DocPage | { title: string; items: DocPage[] })[];
}

export const docsNav: NavGroup[] = [
  {
    title: 'Build Apps',
    items: [
      {
        title: 'Introduction',
        slug: 'introduction',
        description: 'Create apps that extend Nooto\'s capabilities — from custom AI personalities to real-time integrations.',
        content: `## What Are Nooto Apps?

Nooto apps are modular extensions that augment the core functionality of the Nooto platform. They can modify AI behavior, analyze conversations, and connect with external services.

- **Customize AI Behavior** — Create custom AI personalities, alter conversation styles, or add specialized knowledge
- **Real-time Processing** — Process live transcripts as conversations happen
- **External Integrations** — Connect Nooto to Slack, Notion, GitHub, and any external service
- **Earn Revenue** — Publish to the app store and monetize your creations

## Prompt-Based Apps

Customize how Nooto thinks and responds — no server required!

- **Chat Prompts** — Alter Nooto's conversational style and knowledge base. Create expert personas, custom assistants, or specialized advisors. Example: Make Nooto communicate like a fitness coach or financial advisor.
- **Memory Prompts** — Customize how conversations are analyzed and summarized. Extract specific information based on your criteria. Example: Extract action items, key decisions, or meeting notes.

Prompt-based apps are the easiest to create — just define your prompt and you're done!

## Integration Apps

Connect Nooto to external services with webhooks and APIs.

- **Memory Triggers** — Run your code when a memory is created. Perfect for syncing to external tools. Example: Post conversation summaries to Slack or update a CRM.
- **Real-time Transcript** — Process live audio transcripts as they happen. Enable real-time reactions. Example: Trigger smart home actions or live coaching feedback.
- **Chat Tools** — Add custom tools that users can invoke in Nooto chat. Example: "Send a message to #general in Slack" or "Create a GitHub issue".
- **Audio Streaming** — Process raw audio bytes for custom STT, VAD, or audio analysis.

Integration apps require a server endpoint (webhook) to receive data from Nooto.

## Quick Start: Build Your First App in 5 Minutes

Test the integration flow without writing any server code.

1. Go to webhook.site and copy your unique URL
2. Download the Nooto app from the App Store or Google Play
3. In the Nooto app: Explore → Create an App
4. Select a capability (e.g., "Real-time Transcript"), paste your webhook URL, and install
5. Start speaking — watch real-time data appear on webhook.site!

## Example Apps

Learn from real apps built by the community:

- **Hey Nooto** — Ask questions and get answers via notification in real-time
- **Nooto Mentor** — Proactive AI mentor that provides guidance during conversations
- **Slack Integration** — Post conversation summaries and memories to Slack channels
- **Zapier** — Connect Nooto to 5000+ apps through Zapier automations
- **GitHub** — Create issues and manage PRs from your conversations`,
      },
      {
        title: 'Prompt-Based Apps',
        slug: 'prompt-based',
        description: 'Create apps that customize AI personality and memory processing — no server required.',
        content: `## Overview

Prompt-based apps let you customize Nooto's AI behavior without any server infrastructure. There are two types:

- **Chat Prompts** — Change how Nooto responds in conversations
- **Memory Prompts** — Customize how memories are analyzed and summarized

## Chat Prompts

Chat prompts alter Nooto's conversational personality and knowledge base. When a user enables your app, your prompt is injected into Nooto's system prompt.

### How to Create

1. Open the Nooto app
2. Go to Explore → Create an App
3. Select "Chat Prompt"
4. Write your system prompt
5. Test and publish

### Best Practices

- **Be specific** — Clearly define the AI's role, tone, and expertise area
- **Include examples** — Show the AI how to respond in different scenarios
- **Set boundaries** — Define what the AI should and shouldn't do
- **Keep it focused** — One clear persona works better than a complex multi-role prompt

### Example: Fitness Coach

\`\`\`
You are a certified fitness coach and nutritionist. When the user discusses meals, provide calorie estimates and nutritional advice. When they mention workouts, suggest improvements and track progress. Always be encouraging but honest about areas for improvement.
\`\`\`

## Memory Prompts

Memory prompts customize how Nooto processes and categorizes your conversation memories.

### How It Works

After a conversation ends, Nooto creates a "memory" — a structured summary. Memory prompts let you control what gets extracted:

- Custom categories for different types of conversations
- Specific fields to extract (action items, decisions, questions)
- Custom formatting for summaries
- Conditional logic based on conversation content

### Example: Meeting Notes Extractor

\`\`\`
For every conversation, extract the following in structured format:
- Meeting participants (if mentioned)
- Key decisions made
- Action items with owners
- Open questions or unresolved topics
- Follow-up date if mentioned
\`\`\``,
      },
      {
        title: 'Integrations',
        slug: 'integrations',
        description: 'Build webhooks for memory triggers and real-time transcript processing.',
        content: `## Overview

Integration apps connect Nooto to external services using webhooks. When events happen in Nooto (new memory, real-time transcript), your server receives the data and can take action.

## Memory Triggers

Your webhook is called when a memory is created or updated.

### Webhook Payload

Your endpoint receives a POST request with the memory data:

- Memory ID
- Transcript text
- AI-generated summary
- Action items
- Structured data (title, category, etc.)
- Timestamps and metadata

### Use Cases

- **Slack/Discord** — Post summaries to a channel
- **CRM** — Update contact records with meeting notes
- **Notion/Docs** — Create pages with structured notes
- **Task Manager** — Create tasks from action items

## Real-time Transcript

Your webhook receives live transcript segments as conversations happen.

### How It Works

1. User starts a conversation with your app enabled
2. As audio is transcribed, segments are sent to your webhook
3. Your server processes segments and can send responses back
4. Responses appear as notifications to the user

### Payload Format

Each segment includes:

- Session ID
- Transcript text (incremental)
- Speaker info
- Timestamp

### Use Cases

- **Live coaching** — Provide real-time feedback during conversations
- **Smart alerts** — Trigger notifications based on keywords
- **Translation** — Real-time language translation
- **Compliance** — Monitor conversations for regulatory terms

## Setting Up Your Server

Any HTTP server that accepts POST requests works. Popular choices:

- **Python** — FastAPI or Flask
- **Node.js** — Express or Fastify
- **Go** — net/http or Gin

For development, use ngrok to expose your local server:

\`\`\`bash
ngrok http 8000
\`\`\`

Then use the ngrok URL as your webhook endpoint in the Nooto app.`,
      },
      {
        title: 'Chat Tools',
        slug: 'chat-tools',
        description: 'Add custom tools that users can invoke in Nooto conversations.',
        content: `## Overview

Chat tools extend Nooto's AI with custom capabilities. When a user asks Nooto to do something your tool handles, the AI calls your endpoint and uses the result in its response.

## How Chat Tools Work

1. You define a tool with a name, description, and parameters
2. When a user's request matches your tool, Nooto's AI calls it
3. Your server processes the request and returns structured data
4. Nooto incorporates the result into its response

## Defining a Tool

Each tool needs:

- **Name** — A short identifier (e.g., "search_slack")
- **Description** — What the tool does (the AI uses this to decide when to call it)
- **Parameters** — JSON Schema defining the input the tool expects
- **Endpoint** — Your server URL that handles the tool call

### Example: Slack Search Tool

Name: search_slack
Description: Search messages in Slack channels
Parameters: query (string), channel (string, optional)

When a user says "Find the message about the Q4 budget in Slack", Nooto's AI recognizes the intent, calls your tool with the query, and presents the results.

## Building a Tool Server

Your endpoint receives a POST with:

- Tool name
- Parameters (as defined in your schema)
- User context (who's calling)

Return a JSON response with your result. The AI will interpret and present it to the user.

## Best Practices

- **Clear descriptions** — The AI decides when to use your tool based on the description
- **Specific parameters** — Well-defined schemas help the AI pass correct data
- **Fast responses** — Keep response times under 5 seconds
- **Error handling** — Return meaningful error messages the AI can relay to users`,
      },
      {
        title: 'Submitting',
        slug: 'submitting',
        description: 'Submit your app to the Nooto App Store.',
        content: `## Publishing Your App

Once your app is ready, you can submit it to the Nooto App Store for all users to discover and install.

## Requirements

Before submitting, ensure your app meets these criteria:

- **Working endpoint** — If it's an integration app, your webhook must be reliable and responsive
- **Clear description** — Explain what your app does and how to use it
- **Icon** — A square icon (512x512px recommended)
- **Privacy** — Document what data your app accesses and how it's used
- **Testing** — Verify your app works with different conversation types

## Submission Process

1. Open the Nooto app
2. Go to your app's settings
3. Tap "Submit for Review"
4. Fill in the submission form (description, category, screenshots)
5. Submit for review

## Review Process

The Nooto team reviews submissions for:

- **Functionality** — Does the app work as described?
- **Privacy** — Does it handle user data responsibly?
- **Quality** — Is the user experience polished?
- **Guidelines** — Does it follow the Nooto app guidelines?

Reviews typically take 2-3 business days.

## After Approval

Once approved, your app appears in the Nooto App Store. Users can discover, install, and rate your app. You'll receive analytics on installs and usage.`,
      },
    ],
  },
];

export function findDocBySlug(slug: string): DocPage | undefined {
  for (const group of docsNav) {
    for (const item of group.items) {
      if ('slug' in item && item.slug === slug) return item;
      if ('items' in item) {
        const found = item.items.find((sub) => sub.slug === slug);
        if (found) return found;
      }
    }
  }
  return undefined;
}

export function getAllSlugs(): string[] {
  const slugs: string[] = [];
  for (const group of docsNav) {
    for (const item of group.items) {
      if ('slug' in item) slugs.push(item.slug);
      if ('items' in item) {
        for (const sub of item.items) slugs.push(sub.slug);
      }
    }
  }
  return slugs;
}
