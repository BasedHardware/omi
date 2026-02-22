# OpenClaw Plugin for Omi

Official OpenClaw plugin that integrates with [Omi](https://omi.me) to provide seamless access to user memories, conversations, and action items.

## Features

- **Memory Management**: Search, create, update, and delete memories with category organization
- **Conversation Access**: Browse conversation history with optional transcript retrieval
- **Action Items**: Create and manage tasks/todos from Omi
- **Auto Context Injection**: Automatically inject recent memories and conversations into agent context
- **Batch Operations**: Efficiently create multiple memories or action items at once
- **Smart Caching**: TTL-based caching to reduce API calls and improve performance
- **Prompt Injection Protection**: Built-in safeguards against malicious content in memories

## Installation

### From npm (when published)

```bash
npm install -g @openclaw/omi
```

### From source

```bash
cd plugins/openclaw
npm install
npm run build
npm link
```

Then in your OpenClaw configuration, enable the plugin:

```yaml
plugins:
  - omi
```

## Configuration

Add the following to your OpenClaw config:

```yaml
plugins:
  - id: omi
    config:
      apiKey: "omi_dev_your_key_here"
      baseUrl: "https://api.omi.me"  # optional, default shown
      cacheTtlMs: 300000  # optional, 5 minutes default
      autoInject: true  # optional, auto-inject context on session start
```

### Configuration Options

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `apiKey` | string | ✅ Yes | - | Your Omi Developer API key from https://api.omi.me |
| `baseUrl` | string | No | `https://api.omi.me` | Omi API base URL (for custom instances) |
| `cacheTtlMs` | number | No | `300000` | Cache time-to-live in milliseconds (5 min default) |
| `autoInject` | boolean | No | `false` | Automatically inject memories/conversations into context |

### Getting Your API Key

1. Visit https://api.omi.me
2. Sign in with your Omi account
3. Navigate to Developer settings
4. Generate a new API key
5. Copy the key (starts with `omi_dev_`)

## Available Tools

The plugin registers the following tools for OpenClaw agents:

### Memory Tools

- **`omi_memories_search`** - Search through stored memories
  - Parameters: `limit`, `offset`, `categories`
  
- **`omi_memories_create`** - Create a new memory
  - Parameters: `content`, `category`, `visibility`
  
- **`omi_memories_batch`** - Create multiple memories at once
  - Parameters: `memories` (array)

### Conversation Tools

- **`omi_conversations`** - List conversation history
  - Parameters: `limit`, `offset`, `start_date`, `end_date`, `include_transcript`
  
- **`omi_conversation_detail`** - Get detailed conversation info
  - Parameters: `id`, `include_transcript`

### Action Item Tools

- **`omi_action_items`** - List action items/tasks
  - Parameters: `limit`, `offset`, `completed`, `start_date`, `end_date`
  
- **`omi_action_items_create`** - Create a new action item
  - Parameters: `description`, `due_at`
  
- **`omi_action_items_batch`** - Create multiple action items
  - Parameters: `action_items` (array)

## Usage Examples

### Agent Skill Integration

The plugin includes a skill file (`skills/omi/SKILL.md`) that teaches agents how to use Omi naturally. This is automatically loaded by OpenClaw.

### Programmatic Usage

```typescript
import omiPlugin from '@openclaw/omi';

// Plugin is registered automatically by OpenClaw
// Tools are available to the agent
```

### CLI Commands

Currently, this plugin focuses on agent-facing tools. CLI commands may be added in future versions.

## Architecture

```
├── index.ts           # Main plugin entry point and tool registration
├── omi-client.ts      # Omi API client wrapper
├── cache.ts           # TTL cache implementation
├── skills/omi/SKILL.md  # Agent skill documentation
└── README.md          # This file
```

### Key Components

**OmiClient**: Handles all API communication with Omi, including:
- Automatic authentication via Bearer token
- Request/response handling with proper error messages
- Smart caching to reduce redundant API calls
- Support for all Omi Developer API endpoints

**Cache**: Simple TTL-based cache for GET requests:
- Configurable expiration time
- Automatic pruning of expired entries
- Cache bypass for mutations (POST/PATCH/DELETE)

**Security Features**:
- Prompt injection detection and filtering
- HTML entity escaping for injected context
- API key stored securely in config (never logged)
- Input validation on all tool parameters

## API Reference

This plugin uses the [Omi Developer API](https://api.omi.me/docs). Key endpoints:

- `GET /v1/dev/user/memories` - List memories
- `POST /v1/dev/user/memories` - Create memory
- `GET /v1/dev/user/conversations` - List conversations
- `GET /v1/dev/user/action-items` - List action items
- `POST /v1/dev/user/action-items` - Create action item

All endpoints require authentication via `Authorization: Bearer <token>` header.

## Development

### Building

```bash
npm run build
```

### Development Mode (watch)

```bash
npm run dev
```

### Clean Build Artifacts

```bash
npm run clean
```

## Contributing

This plugin is maintained as part of the Omi project. Contributions are welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Related Issues

- GitHub Issue: https://github.com/BasedHardware/omi/issues/4939

## License

MIT

## Support

- Omi Documentation: https://omi.me/docs
- API Documentation: https://api.omi.me/docs
- OpenClaw Documentation: https://openclaw.dev
- Report issues: https://github.com/BasedHardware/omi/issues
