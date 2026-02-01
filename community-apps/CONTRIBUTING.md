# Contributing to Omi Community Apps

Thank you for your interest in contributing to the Omi Community Apps ecosystem! This guide provides technical details for developers.

## Quick Start Checklist

- [ ] Read the [main README](./README.md)
- [ ] Fork the Omi repository
- [ ] Copy the `TEMPLATE/` directory
- [ ] Implement your app
- [ ] Test locally
- [ ] Update `registry.json`
- [ ] Create a Pull Request
- [ ] Pass CI checks
- [ ] Respond to review feedback
- [ ] Get approved and merged!

## App Development Workflow

### 1. Environment Setup

```bash
# Clone your fork
git clone https://github.com/YourUsername/omi.git
cd omi

# Create a new branch
git checkout -b add-app-your-app-name

# Set up Python environment
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create App Structure

```bash
# Create your app directory
mkdir -p community-apps/your-github-username/your-app-name
cd community-apps/your-github-username/your-app-name

# Copy template
cp -r ../../TEMPLATE/* .

# Start editing
code .  # Or your preferred editor
```

### 3. Implement Your App

#### Edit `app.json`

Update all required fields. Use the schema for validation:

```bash
# Validate your app.json (requires jsonschema)
pip install jsonschema
python -c "
import json
import jsonschema

with open('app.json') as f:
    app = json.load(f)
with open('../../app-schema.json') as f:
    schema = json.load(f)

jsonschema.validate(app, schema)
print('✅ app.json is valid')
"
```

#### Write Your Code

**For Memory Apps** (triggered after conversation):

```python
from fastapi import APIRouter
from models import Conversation, EndpointResponse

router = APIRouter()

@router.post('/your-endpoint', response_model=EndpointResponse)
def your_function(conversation: Conversation):
    # Access transcript
    transcript = conversation.get_transcript()

    # Access structured data
    structured = conversation.structured.dict()

    # Access segments
    for segment in conversation.transcript_segments:
        print(f"{segment.speaker}: {segment.text}")

    # Process and return
    return EndpointResponse(
        message="Your notification message"
    )
```

**For Proactive Notification Apps** (real-time):

```python
from models import ProactiveNotificationEndpointResponse

@router.post('/realtime-endpoint')
def realtime_function(data: dict):
    session_id = data['session_id']
    segments = data['segments']  # List of recent transcript segments

    # Check for trigger conditions
    should_notify = check_condition(segments)

    if should_notify:
        return ProactiveNotificationEndpointResponse(
            prompt="Your notification template with {{user_name}}",
            params=["user_name", "user_facts"],
            context={
                "topics": ["topic1", "topic2"],
                "people": ["person_name"]
            }
        )

    # Return empty if no notification needed
    return ProactiveNotificationEndpointResponse(
        prompt=None,
        params=[],
        context={}
    )
```

#### Available Models

Import from `plugins/example/models.py`:

```python
from models import (
    # Request models
    Conversation,
    TranscriptSegment,
    Memory,
    Structured,

    # Response models
    EndpointResponse,
    ProactiveNotificationEndpointResponse,

    # App models
    App,
    ExternalIntegration,
    ChatTool,
    ProactiveNotification
)
```

**Conversation Model:**
```python
class Conversation:
    id: str
    transcript_segments: List[TranscriptSegment]
    memories: List[Memory]
    structured: Structured
    created_at: datetime
    finished_at: datetime
    photos: List[Photo]  # If conversation has photos

    def get_transcript(self) -> str:
        # Returns full transcript text
```

**TranscriptSegment Model:**
```python
class TranscriptSegment:
    text: str
    speaker: str  # 'SPEAKER_0', 'SPEAKER_1', etc.
    speaker_id: int
    is_user: bool
    start: float  # Timestamp in seconds
    end: float
```

### 4. Add Dependencies

Only include what you actually need:

```txt
# requirements.txt

# Required by Omi (already available)
fastapi>=0.109.0
pydantic>=2.5.0

# Add your additional dependencies
requests>=2.31.0
openai>=1.10.0  # If using OpenAI
anthropic>=0.25.0  # If using Claude
```

**Dependency Guidelines:**
- Pin versions: `package>=1.0.0,<2.0.0`
- Avoid heavy packages (TensorFlow, PyTorch) unless necessary
- Check package popularity and maintenance on PyPI
- Scan for security vulnerabilities

### 5. Write Tests (Optional but Recommended)

Create `test_main.py`:

```python
import pytest
from fastapi.testclient import TestClient
from main import router

client = TestClient(router)

def test_your_endpoint():
    # Mock conversation data
    conversation = {
        "id": "test-id",
        "transcript_segments": [
            {
                "text": "Hello world",
                "speaker": "SPEAKER_0",
                "start": 0.0,
                "end": 1.0
            }
        ]
    }

    response = client.post("/your-endpoint", json=conversation)
    assert response.status_code == 200
    assert "message" in response.json()
```

Run tests:
```bash
pytest test_main.py -v
```

### 6. Update Registry

Add your app to `community-apps/registry.json`:

```json
{
  "apps": [
    // ... existing apps ...
    {
      "id": "your-username/your-app-name",
      "name": "Your App Name",
      "author": "Your Name",
      "email": "your@email.com",
      "description": "What your app does",
      "category": "conversation-analysis",
      "capabilities": ["memories"],
      "status": "under-review",
      "version": "1.0.0",
      "path": "community-apps/your-username/your-app-name",
      "image": "https://raw.githubusercontent.com/BasedHardware/omi/main/community-apps/your-username/your-app-name/logo.png",
      "triggers": ["memory_creation"],
      "official": false,
      "private": false,
      "approved": false,
      "rating_avg": 0,
      "rating_count": 0,
      "installs": 0
    }
  ]
}
```

**Important:** Keep existing apps in the registry, just add yours to the array.

### 7. Local Testing

#### Option A: Test with Backend

```bash
# Terminal 1: Start Omi backend
cd backend
uvicorn main:app --reload

# Terminal 2: Test your endpoint
curl -X POST http://localhost:8000/v1/apps/your-username/your-app-name/your-endpoint \
  -H "Content-Type: application/json" \
  -d @test-conversation.json
```

#### Option B: Test Standalone

```bash
# Run just your app
cd community-apps/your-username/your-app-name
python -m uvicorn main:app --reload --port 8001

# Test it
curl -X POST http://localhost:8001/your-endpoint \
  -H "Content-Type: application/json" \
  -d @test-conversation.json
```

### 8. Create Pull Request

```bash
# Stage your changes
git add community-apps/your-username/
git add community-apps/registry.json

# Commit with clear message
git commit -m "Add community app: Your App Name

- Implements [capability]
- Triggers on [event]
- Provides [value proposition]
"

# Push to your fork
git push origin add-app-your-app-name
```

Then:
1. Go to https://github.com/BasedHardware/omi
2. Click "New Pull Request"
3. Select your branch
4. Fill in the PR template
5. Submit!

## Code Style Guidelines

### Python (PEP 8)

```python
# Good
def process_conversation(conversation: Conversation) -> EndpointResponse:
    """Process a conversation and return feedback."""
    transcript = conversation.get_transcript()
    return EndpointResponse(message="Done")

# Bad
def processConversation(conv):
    trans = conv.get_transcript()
    return {"message": "Done"}
```

**Rules:**
- Use `black` formatter: `black --line-length 120 main.py`
- Type hints for all functions
- Docstrings for public functions
- Descriptive variable names
- Max line length: 120 characters

### Error Handling

Always handle errors gracefully:

```python
from fastapi import HTTPException

@router.post('/endpoint')
def endpoint(conversation: Conversation):
    try:
        # Your logic
        result = process(conversation)
        return EndpointResponse(message=result)
    except ValueError as e:
        # Log and return user-friendly error
        print(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid input")
    except Exception as e:
        # Catch-all for unexpected errors
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Processing failed")
```

### Logging

Use Python's logging module:

```python
import logging

logger = logging.getLogger(__name__)

@router.post('/endpoint')
def endpoint(conversation: Conversation):
    logger.info(f"Processing conversation {conversation.id}")
    # Your logic
    logger.debug(f"Transcript length: {len(conversation.get_transcript())}")
    return EndpointResponse(message="Done")
```

## CI/CD Pipeline

When you create a PR, automated checks run:

### 1. Schema Validation

Validates `app.json` against `app-schema.json`:
- All required fields present
- Correct data types
- Valid enum values
- Proper version format

### 2. File Structure Check

Ensures required files exist:
- `app.json` ✅
- `main.py` ✅
- `README.md` ✅
- `requirements.txt` ✅
- `logo.png` (or `.jpg`, `.svg`) ✅

### 3. Code Quality

Runs linters and formatters:
- `black --check main.py` (formatting)
- `flake8 main.py` (style)
- `mypy main.py` (type checking)

### 4. Security Scan

Checks for vulnerabilities:
- Dependency vulnerabilities (via `safety`)
- Known malware patterns
- Suspicious code (arbitrary execution, file access)

### 5. Registry Validation

Ensures `registry.json`:
- Valid JSON format
- No duplicate app IDs
- All paths exist
- Image URLs are reachable

## Common Issues & Solutions

### Issue: Import Errors

```
ImportError: cannot import name 'Conversation' from 'models'
```

**Solution:** Use correct import path:
```python
# Add plugins/example to path
import sys
from pathlib import Path
plugins_path = Path(__file__).parent.parent.parent.parent / 'plugins' / 'example'
sys.path.insert(0, str(plugins_path))

from models import Conversation
```

### Issue: CI Fails on Schema Validation

```
ValidationError: 'id' is required
```

**Solution:** Ensure all required fields in `app.json`:
```json
{
  "id": "username/app-name",  // Must match: author/name
  "name": "...",
  "author": "...",
  "email": "...",
  "description": "...",
  "category": "...",
  "capabilities": [...],
  "version": "1.0.0"
}
```

### Issue: Import Works Locally But Fails in CI

**Solution:** Pin all dependencies with versions:
```txt
# Bad
requests

# Good
requests>=2.31.0,<3.0.0
```

### Issue: App Not Appearing in Marketplace

**Solution:** Check:
1. `status` is `"approved"` in registry
2. `approved` is `true` in registry
3. `private` is `false` in registry
4. Backend was restarted after merge

## Advanced Topics

### Accessing User Settings

Apps can store user-specific settings:

```python
@router.post('/endpoint')
def endpoint(conversation: Conversation, user_settings: dict):
    api_key = user_settings.get('api_key')
    webhook_url = user_settings.get('webhook_url')

    # Use settings in your logic
```

### External API Integration

Best practices for calling external APIs:

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure retries
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

@router.post('/endpoint')
def endpoint(conversation: Conversation):
    try:
        response = session.post(
            'https://api.example.com/endpoint',
            json={'data': conversation.get_transcript()},
            timeout=10  # Always set timeout
        )
        response.raise_for_status()
        return EndpointResponse(message="Success")
    except requests.RequestException as e:
        logger.error(f"API call failed: {e}")
        raise HTTPException(status_code=502, detail="External service unavailable")
```

### Caching Results

Use Redis for caching (available in backend):

```python
from database.redis_db import r

@router.post('/endpoint')
def endpoint(conversation: Conversation):
    # Check cache
    cache_key = f"app:your-app:{conversation.id}"
    cached = r.get(cache_key)

    if cached:
        return EndpointResponse(message=cached.decode())

    # Process
    result = expensive_computation(conversation)

    # Cache for 1 hour
    r.setex(cache_key, 3600, result)

    return EndpointResponse(message=result)
```

### Using Omi's LLM Infrastructure

Leverage Omi's configured LLM clients:

```python
from langchain_openai import ChatOpenAI

chat = ChatOpenAI(model='gpt-4o', temperature=0)

@router.post('/endpoint')
def endpoint(conversation: Conversation):
    prompt = f"Analyze this: {conversation.get_transcript()}"
    response = chat.invoke(prompt)

    return EndpointResponse(message=response.content)
```

## Support & Community

### Getting Help

1. **Check documentation**: [docs.omi.me](https://docs.omi.me)
2. **Search issues**: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
3. **Ask in Discord**: [discord.gg/omi](https://discord.gg/omi) (#app-development channel)
4. **Email support**: team@basedhardware.com

### Reporting Bugs

Found a bug in an existing app? Report it:

1. Go to the app's directory
2. Check if issue already exists
3. Create detailed bug report with:
   - Steps to reproduce
   - Expected vs actual behavior
   - Error messages
   - Your environment (OS, Python version, etc.)

### Requesting Features

Want a feature in the platform? Open a feature request:

1. Check existing feature requests
2. Describe the use case
3. Explain the benefit
4. Suggest implementation (optional)

## Recognition & Rewards

Top contributors get:
- Featured in Omi newsletter
- Twitter shoutout from @BasedHardware
- Special contributor role in Discord
- Early access to new features
- Potential partnership opportunities

## License & Legal

### App Licensing

- All community apps must be **open source**
- Recommended licenses: MIT, Apache 2.0, GPL-3.0
- Include `LICENSE` file in your app directory
- You retain all rights to your code

### Code of Conduct

By contributing, you agree to:
- Be respectful and inclusive
- No harassment or discrimination
- Constructive feedback only
- Follow Omi's community guidelines

### Intellectual Property

- You own your app code
- Omi can distribute your app via the marketplace
- Users can use your app per your chosen license
- You can monetize your app

## Changelog

When updating your app, document changes:

### README.md Changelog Section

```markdown
## Changelog

### v1.1.0 (2026-02-15)
- Added support for real-time processing
- Fixed bug with empty transcripts
- Improved error messages

### v1.0.0 (2026-02-01)
- Initial release
- Basic conversation analysis
- Notification support
```

### Semantic Versioning

Follow semver: `MAJOR.MINOR.PATCH`

- **PATCH** (1.0.1): Bug fixes, no new features
- **MINOR** (1.1.0): New features, backward compatible
- **MAJOR** (2.0.0): Breaking changes

## Thank You! 🙏

Your contributions make Omi better for everyone. We're excited to see what you build!

**Questions?** Open an issue or reach out in Discord.

**Happy coding! 🚀**
