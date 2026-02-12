# Twitter vs GitHub Issues App - Key Differences

## Overview

Both apps follow the same architecture pattern but are customized for their respective platforms.

## Architecture Similarities

✅ FastAPI backend
✅ File-based storage with Railway persistence
✅ OAuth 2.0 authentication
✅ OMI webhook integration
✅ AI-powered content processing (OpenAI)
✅ Mobile-first UI
✅ Session management for segment collection

## Key Differences

### 1. **Segment Collection**

| Feature | Twitter App | GitHub App |
|---------|-------------|------------|
| Trigger phrase | "Tweet Now" | "Feedback Post" |
| Segments collected | 3 | 5 |
| Reasoning | Quick tweets (10-15s) | Detailed issues (15-20s) |

### 2. **Authentication**

| Feature | Twitter App | GitHub App |
|---------|-------------|------------|
| OAuth Provider | Twitter OAuth 2.0 (Tweepy) | GitHub OAuth 2.0 (direct) |
| Scopes | tweet.read, tweet.write, users.read | repo |
| Token Refresh | Automatic refresh token handling | No refresh (long-lived tokens) |
| OAuth Library | Tweepy's OAuth2UserHandler | Direct requests |

### 3. **Content Processing**

| Feature | Twitter App | GitHub App |
|---------|-------------|------------|
| AI Output | Single cleaned tweet text | Title + Description |
| Formatting | Tweet cleanup (280 chars) | Professional issue format |
| Extra features | Filler word removal | Structure: problem, context, details |

### 4. **User Settings**

| Feature | Twitter App | GitHub App |
|---------|-------------|------------|
| Configuration | None (just auth) | Repository selection |
| Homepage | Simple instructions | Full settings page |
| Settings Updates | N/A | Change repo anytime |
| Repo Management | N/A | Refresh repos, select target |

### 5. **Output**

| Feature | Twitter App | GitHub App |
|---------|-------------|------------|
| Creates | Tweet on Twitter | Issue on GitHub |
| Returns | Tweet text + ID | Issue title + number + URL |
| Labels | N/A | Adds "voice-feedback" label |
| Format | Single text string | Title + multi-line description |

## File Structure Comparison

### Twitter App (`/apps/twitter/`)
```
main_simple.py          # Main FastAPI app
twitter_client.py       # Twitter API with Tweepy
tweet_detector.py       # Tweet extraction + AI cleanup
simple_storage.py       # Users + sessions storage
```

### GitHub App (`/apps/github/`)
```
main.py                 # Main FastAPI app + mobile UI
github_client.py        # GitHub API (direct requests)
issue_detector.py       # Issue generation + AI formatting
simple_storage.py       # Users + sessions + repo prefs
```

## UI Differences

### Twitter App
- Minimal setup page
- Just "Connect Twitter" button
- Focus on quick start

### GitHub App
- Full settings dashboard
- Repository dropdown selector
- "Save Repository" and "Refresh Repos" buttons
- Mobile-first responsive design with GitHub color scheme
- Step-by-step usage guide
- Settings management UI

## Code Examples

### Twitter: Processing
```python
# Collect 3 segments
if segments_count >= 3:
    # AI extracts single tweet
    cleaned_content = await tweet_detector.ai_extract_tweet_from_segments(accumulated)
    # Post tweet
    result = await twitter_client.post_tweet(access_token, cleaned_content)
```

### GitHub: Processing
```python
# Collect 5 segments
if segments_count >= 5:
    # AI generates title + description
    title, description = await issue_detector.ai_generate_issue_from_segments(accumulated)
    # Create issue
    result = await github_client.create_issue(access_token, repo_full_name, title, description)
```

## Storage Differences

### Twitter
```python
users[uid] = {
    "uid": uid,
    "access_token": ...,
    "refresh_token": ...,
    "expires_at": ...
}
```

### GitHub
```python
users[uid] = {
    "uid": uid,
    "access_token": ...,
    "github_username": ...,
    "selected_repo": ...,        # NEW: repo selection
    "available_repos": [...]     # NEW: repo list
}
```

## AI Prompts Comparison

### Twitter
- **Goal:** Clean up tweet, remove filler words
- **Output:** Single text string (280 chars max)
- **Focus:** Natural, concise, well-formatted tweet

### GitHub
- **Goal:** Extract problem and format professionally
- **Output:** Title (concise) + Description (detailed)
- **Focus:** Clear problem statement, context, technical details

## Mobile-First UI

### Twitter App
- Basic HTML with inline styles
- Centered cards
- Simple gradient background

### GitHub App
- Comprehensive CSS with GitHub theming
- Dark gradient background (#24292e)
- Step-by-step visual guides
- Responsive cards and buttons
- Repository management interface
- Status indicators (connected/disconnected)

## Deployment

Both apps:
- ✅ Deploy to Railway
- ✅ Use persistent `/app/data` volume
- ✅ Environment variables for secrets
- ✅ Health check endpoints
- ✅ Same Python version (3.10.17)

## Summary

The GitHub app is essentially the Twitter app enhanced with:
1. **5 segments** instead of 3 (more detail needed)
2. **Repository selection** (multi-project support)
3. **Title + Description** generation (structured output)
4. **Settings management UI** (change repos after setup)
5. **Mobile-first design** (better UX)
6. **Direct OAuth** (no library dependency like Tweepy)

