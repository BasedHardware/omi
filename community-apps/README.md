# Omi Community Apps

Welcome to the Omi Community Apps ecosystem! This directory contains all community-contributed apps for the Omi platform. All apps here are **open source and auditable** by the community.

## 📋 Table of Contents

- [What are Omi Apps?](#what-are-omi-apps)
- [Submitting Your App](#submitting-your-app)
- [App Structure](#app-structure)
- [Development Guide](#development-guide)
- [Review Process](#review-process)
- [Auto-Deployment](#auto-deployment)
- [App Capabilities](#app-capabilities)
- [Examples](#examples)

## 🤔 What are Omi Apps?

Omi Apps extend your Omi device's capabilities by processing conversations, providing insights, sending notifications, and integrating with external services. Apps can:

- **Analyze conversations** after they finish (e.g., extract action items, provide feedback)
- **Process real-time transcripts** as you talk (e.g., live coaching, keyword detection)
- **Provide chat functionality** (e.g., custom AI assistants, personas)
- **Integrate with external services** (e.g., Notion, Slack, Zapier)
- **Send proactive notifications** (e.g., reminders, insights, alerts)

## 🚀 Submitting Your App

### Prerequisites

- GitHub account
- Basic knowledge of Python (FastAPI) or Node.js
- Your app code and assets ready
- Clear app description and documentation

### Submission Steps

1. **Fork the Omi repository**
   ```bash
   git clone https://github.com/YourUsername/omi.git
   cd omi
   ```

2. **Create your app directory**
   ```bash
   mkdir -p community-apps/your-github-username/your-app-name
   cd community-apps/your-github-username/your-app-name
   ```

3. **Copy the template**
   ```bash
   cp -r ../../TEMPLATE/* .
   ```

4. **Develop your app**
   - Edit `app.json` with your app metadata
   - Implement your logic in `main.py` (or other files)
   - Update `requirements.txt` with dependencies
   - Write clear documentation in `README.md`
   - Add a logo image (`logo.png` recommended, max 512x512px)

5. **Update the registry**

   Add your app to `community-apps/registry.json`:
   ```json
   {
     "id": "your-github-username/your-app-name",
     "name": "Your App Name",
     "author": "Your Name",
     "email": "your@email.com",
     "description": "Clear description of what your app does",
     "category": "conversation-analysis",
     "capabilities": ["memories"],
     "status": "under-review",
     "version": "1.0.0",
     "path": "community-apps/your-github-username/your-app-name",
     "image": "https://raw.githubusercontent.com/BasedHardware/omi/main/community-apps/your-github-username/your-app-name/logo.png",
     "triggers": ["memory_creation"],
     "official": false,
     "private": false,
     "approved": false
   }
   ```

6. **Create a Pull Request**
   ```bash
   git checkout -b add-app-your-app-name
   git add community-apps/
   git commit -m "Add community app: Your App Name"
   git push origin add-app-your-app-name
   ```

7. **Wait for review**
   - The Omi team will review your submission
   - CI checks will validate your app structure
   - You may receive feedback or change requests
   - Once approved, your app will be merged and deployed!

## 📁 App Structure

Each app must follow this structure:

```
community-apps/
└── your-github-username/
    └── your-app-name/
        ├── app.json              # Required: App metadata
        ├── main.py               # Required: Main app code
        ├── requirements.txt      # Required: Python dependencies
        ├── README.md             # Required: Documentation
        ├── logo.png              # Required: App icon (512x512px recommended)
        ├── setup_instructions.md # Optional: Setup guide for users
        ├── .gitignore            # Optional: Git ignore rules
        └── ...                   # Optional: Additional code files
```

### Required Files

#### `app.json`

App metadata and configuration. See `app-schema.json` for full schema.

**Minimum required fields:**
```json
{
  "id": "username/app-name",
  "name": "App Name",
  "author": "Your Name",
  "email": "your@email.com",
  "description": "What your app does (20-200 chars)",
  "category": "conversation-analysis",
  "capabilities": ["memories"],
  "version": "1.0.0"
}
```

#### `main.py`

Your app's main code. Must export a FastAPI router:

```python
from fastapi import APIRouter
from models import Conversation, EndpointResponse

router = APIRouter()

@router.post('/your-endpoint')
def your_function(conversation: Conversation):
    # Your logic here
    return EndpointResponse(message="Your message")
```

#### `requirements.txt`

Python package dependencies. Keep it minimal:

```txt
fastapi>=0.109.0
# Add only what you need
```

#### `README.md`

Documentation for users. Should include:
- What your app does
- How it works
- Setup instructions (if any)
- Privacy/data policy
- Support contact

#### `logo.png`

App icon displayed in the Omi app marketplace. Requirements:
- Format: PNG, JPG, or SVG
- Size: 512x512px recommended
- Max file size: 1MB
- Square aspect ratio

## 🛠 Development Guide

### Local Development

1. **Set up the backend**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. **Run the backend**
   ```bash
   uvicorn main:app --reload
   ```

3. **Test your app**
   ```bash
   curl -X POST http://localhost:8000/v1/your-app-endpoint \
     -H "Content-Type: application/json" \
     -d @test-conversation.json
   ```

### Testing Guidelines

- Test with various conversation lengths (short, medium, long)
- Test with empty/null data
- Ensure error handling works properly
- Verify your app doesn't crash the backend
- Check memory usage for large conversations

### Code Quality

Your app will be checked for:
- **Security**: No malicious code, safe dependency versions
- **Performance**: Efficient processing, no infinite loops
- **Quality**: Clean code, proper error handling
- **Privacy**: Clear data usage policy
- **Documentation**: Comprehensive README

## ✅ Review Process

### Automated Checks (CI)

When you submit a PR, automated checks will validate:
1. ✅ `app.json` follows the schema
2. ✅ Required files exist (`main.py`, `README.md`, `logo.png`, `requirements.txt`)
3. ✅ Registry entry is valid
4. ✅ No malicious code patterns detected
5. ✅ Dependencies are from trusted sources
6. ✅ Python code passes linting

### Manual Review

The Omi team will review:
1. **Functionality**: Does it work as described?
2. **Value**: Is it useful for Omi users?
3. **Safety**: No security vulnerabilities?
4. **Privacy**: Clear data usage disclosure?
5. **Quality**: Well-documented and maintainable?

### Review Timeline

- **Initial feedback**: 1-3 business days
- **Approval/rejection**: 3-7 business days
- **Deployment**: Immediately after merge

### Status Updates

Check your PR for status updates:
- `under-review`: Being reviewed by the team
- `changes-requested`: Needs updates before approval
- `approved`: Ready to merge!
- `rejected`: Not approved (with reasons)

## 🚢 Auto-Deployment

Once your app is approved and merged:

1. **Registry Update**: Your app appears in `registry.json`
2. **Backend Integration**: Auto-loaded into Omi backend
3. **Marketplace**: Visible in the Omi mobile app
4. **Users**: Can install and use immediately!

### Versioning

To update your app:
1. Increment version in `app.json` (follow semver: `1.0.0` → `1.1.0`)
2. Update changelog in `README.md`
3. Create a PR with your changes
4. After approval, users get the update automatically

## 🎨 App Capabilities

### 1. Memories (Conversation Analysis)

Triggered after a conversation finishes. Processes full transcript and structured data.

**Use cases:**
- Extract action items
- Provide conversation feedback
- Analyze sentiment
- Rate conversation quality

**Configuration:**
```json
{
  "capabilities": ["memories"],
  "triggers": ["memory_creation"],
  "memory_prompt": "Your analysis prompt here..."
}
```

### 2. Chat

Adds custom chat functionality or personas to Omi's chat mode.

**Use cases:**
- Custom AI assistants
- Personality clones
- Domain-specific chatbots
- Integration with external LLMs

**Configuration:**
```json
{
  "capabilities": ["chat"],
  "chat_prompt": "Your chat personality prompt...",
  "chat_tools": [
    {
      "name": "your_tool",
      "description": "What it does",
      "endpoint": "/tools/your-tool",
      "method": "POST"
    }
  ]
}
```

### 3. Proactive Notifications

Processes real-time transcripts and sends timely notifications.

**Use cases:**
- Live conversation coaching
- Keyword alerts
- Context-aware reminders
- Real-time insights

**Configuration:**
```json
{
  "capabilities": ["proactive_notification"],
  "triggers": ["transcript_processed"],
  "proactive_notification": {
    "scopes": ["user_name", "user_facts", "user_context"]
  }
}
```

### 4. External Integration

Integrates with external services via webhooks.

**Use cases:**
- CRM updates (Notion, HubSpot)
- Team communication (Slack, Discord)
- Automation (Zapier, Make)
- Custom backends

**Configuration:**
```json
{
  "capabilities": ["external_integration"],
  "external_integration": {
    "triggers_on": "memory_creation",
    "webhook_url": "https://your-service.com/webhook",
    "auth_steps": [
      {
        "name": "api_key",
        "display_name": "API Key",
        "type": "api_key",
        "instructions": "Get your API key from..."
      }
    ]
  }
}
```

## 📚 Examples

### Simple Memory App

Counts words in conversations:

```python
from fastapi import APIRouter
from models import Conversation, EndpointResponse

router = APIRouter()

@router.post('/word-counter')
def word_counter(conversation: Conversation):
    transcript = conversation.get_transcript()
    word_count = len(transcript.split())

    return EndpointResponse(
        message=f"This conversation had {word_count} words!"
    )
```

### Real-time Notification App

Detects keywords in real-time:

```python
from fastapi import APIRouter
from models import ProactiveNotificationEndpointResponse

router = APIRouter()

@router.post('/keyword-alert')
def keyword_alert(data: dict):
    segments = data.get('segments', [])
    keywords = ['important', 'urgent', 'deadline']

    for segment in segments:
        for keyword in keywords:
            if keyword in segment['text'].lower():
                return ProactiveNotificationEndpointResponse(
                    prompt=f"Keyword detected: {keyword}",
                    params=[],
                    context={}
                )

    return ProactiveNotificationEndpointResponse(
        prompt=None,
        params=[],
        context={}
    )
```

### External Integration App

Sends data to a webhook:

```python
import requests
from fastapi import APIRouter
from models import Conversation, EndpointResponse

router = APIRouter()

@router.post('/webhook-forwarder')
def webhook_forwarder(conversation: Conversation):
    # Get user's webhook URL from app settings
    webhook_url = "https://user-configured-url.com/webhook"

    # Send conversation data
    response = requests.post(
        webhook_url,
        json={
            'transcript': conversation.get_transcript(),
            'structured': conversation.structured.dict()
        }
    )

    return EndpointResponse(
        message="Data sent to your webhook!"
    )
```

## 🔐 Security & Privacy

### Data Handling

- **Be transparent**: Clearly document what data your app uses
- **Minimize data**: Only request access to what you need
- **Secure transmission**: Use HTTPS for all external requests
- **No storage**: Don't store user data unless absolutely necessary
- **User control**: Allow users to delete their data

### Dependencies

- **Trusted sources**: Only use well-known packages from PyPI/npm
- **Version pinning**: Specify exact versions in `requirements.txt`
- **Regular updates**: Keep dependencies up to date
- **Security scans**: CI will scan for known vulnerabilities

### Code Safety

Prohibited:
- ❌ Executing arbitrary code from user input
- ❌ Accessing system files outside app directory
- ❌ Making unauthorized network requests
- ❌ Cryptocurrency mining
- ❌ Malware, spyware, or tracking

## 💰 Monetization

You can create paid apps! Set in `app.json`:

```json
{
  "is_paid": true,
  "price": 999,
  "payment_plan": "one-time",
  "payment_link": "https://your-stripe-link.com"
}
```

Pricing:
- `price`: Amount in cents (999 = $9.99)
- Omi takes 0% commission currently
- You handle payment processing (Stripe, Gumroad, etc.)
- Provide `payment_link` for users to purchase

## 📞 Support

- **Documentation**: [docs.omi.me](https://docs.omi.me)
- **GitHub Issues**: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
- **Discord**: [discord.gg/omi](https://discord.gg/omi)
- **Email**: team@basedhardware.com

## 📜 License

All community apps must be open source. We recommend MIT or Apache 2.0 licenses.

## 🙏 Contributing

Thank you for contributing to the Omi ecosystem! Every app makes Omi more powerful for everyone.

**Happy building! 🚀**
