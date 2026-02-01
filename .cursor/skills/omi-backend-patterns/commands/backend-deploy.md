# Backend Deploy

Deployment checklist and commands for the Omi backend.

## Purpose

Deploy the Omi backend to production with proper verification and monitoring.

## Pre-Deployment Checklist

1. **Run tests**
   ```bash
   cd backend
   ./test.sh
   ```

2. **Check environment variables**
   - Verify all required variables are set
   - Check API keys are valid
   - Ensure secrets are properly configured

3. **Review code changes**
   - Code review completed
   - All tests passing
   - Documentation updated

## Deployment Options

### Modal Deployment

The backend is configured for Modal deployment.

**Deployment**:
```bash
cd backend
modal deploy
```

**Configuration**: See `backend/modal/` directory

### Manual Deployment

1. **Build Docker image**
   ```bash
   docker build -t omi-backend .
   ```

2. **Run container**
   ```bash
   docker run -p 8000:8000 --env-file .env omi-backend
   ```

## Environment Variables

Ensure all required environment variables are set:

**Required**:
- `OPENAI_API_KEY`
- `DEEPGRAM_API_KEY`
- `PINECONE_API_KEY`
- `REDIS_DB_HOST`, `REDIS_DB_PORT`, `REDIS_DB_PASSWORD`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `ENCRYPTION_SECRET`

**OAuth**:
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY`

## Post-Deployment

1. **Verify deployment**
   - Check health endpoint
   - Test API endpoints
   - Verify WebSocket connections

2. **Monitor logs**
   - Check for errors
   - Monitor performance
   - Watch for rate limits

3. **Update documentation**
   - Update API base URL if changed
   - Update deployment docs

## Related Documentation

- Backend Setup: `.cursor/commands/backend-setup.md`
- Backend Architecture: `.cursor/rules/backend-architecture.mdc`

## Related Cursor Resources

### Rules
- `.cursor/rules/backend-architecture.mdc` - System architecture
- `.cursor/rules/backend-testing.mdc` - Testing before deployment
- `.cursor/rules/memory-management.mdc` - Memory management

### Skills
- `.cursor/skills/omi-backend-patterns/` - Backend patterns

### Commands
- `/backend-setup` - Setup backend environment
- `/backend-test` - Run tests before deployment
- `/code-review` - Review code before deployment
