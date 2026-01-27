# Test Integration

Test webhook integrations and plugin functionality.

## Purpose

Test Omi plugin webhooks and integrations to ensure they work correctly.

## Testing Webhooks

### Using webhook.site

1. **Get webhook URL**
   - Go to https://webhook.site
   - Copy your unique URL

2. **Register webhook in Omi app**
   - Open Omi app
   - Navigate to Explore → Create an App
   - Select capability (e.g., "Real-time Transcript")
   - Paste webhook.site URL
   - Install app

3. **Test webhook**
   - Start speaking in Omi app
   - Watch webhook.site for incoming requests
   - Verify payload structure

### Testing Locally

1. **Set up local server**
   ```bash
   # Python
   python -m http.server 8000
   
   # Node.js
   npx http-server -p 8000
   ```

2. **Expose via Ngrok**
   ```bash
   ngrok http 8000
   ```

3. **Use Ngrok URL in Omi app**

## Testing Plugin Endpoints

### Memory Creation Webhook

```bash
# Test webhook endpoint
curl -X POST http://localhost:3000/webhook/memory-created \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test_123",
    "content": "Test memory",
    "category": "personal",
    "user_id": "test_user"
  }'
```

### Real-time Transcript Webhook

```bash
# Test transcript webhook
curl -X POST http://localhost:3000/webhook/transcript \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello world",
    "timestamp": 1234567890,
    "conversation_id": "conv_123",
    "user_id": "test_user"
  }'
```

## Testing OAuth Flows

1. **Set up OAuth provider**
   - Configure OAuth app in provider console
   - Set redirect URIs

2. **Test authorization flow**
   - Initiate OAuth flow
   - Verify callback handling
   - Test token storage

## Integration Testing Checklist

- [ ] Webhook receives correct payload
- [ ] Webhook processes data correctly
- [ ] Error handling works
- [ ] Rate limiting works (if implemented)
- [ ] OAuth flow completes successfully
- [ ] API calls to Omi work correctly

## Related Documentation

- Create Plugin: `.cursor/commands/create-plugin.md`
- Plugin Development: `.cursor/rules/plugin-development.mdc`
- Integrations: `docs/doc/developer/apps/Integrations.mdx`

## Related Cursor Resources

### Rules
- `.cursor/rules/plugin-development.mdc` - Plugin development patterns
- `.cursor/rules/backend-api-patterns.mdc` - Backend API patterns

### Skills
- `.cursor/skills/omi-plugin-development/` - Plugin development workflows
- `.cursor/skills/omi-api-integration/` - API integration patterns

### Subagents
- `.cursor/agents/plugin-developer/` - Plugin development specialist

### Commands
- `/create-plugin` - Create plugin to test
- `/create-app` - Create app to test
