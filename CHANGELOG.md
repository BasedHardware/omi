# Omi Changelog

## What's New

This document summarizes the recent major changes across the Omi platform: Backend, Web Admin, and Flutter App.

---

## Backend

### New Integrations & Tools

The backend now supports a comprehensive suite of third-party integrations accessible through the chat interface:

- **Google Calendar** - Full calendar management including viewing events, creating meetings, updating details, and removing attendees. Calendar events are synced to Firestore for faster access.

- **Google Gmail** - Email tools for reading and composing messages directly from chat.

- **GitHub** - Complete GitHub integration for repository management, issues, and pull requests.

- **Notion** - Access and manage Notion databases and pages through conversational commands.

- **Twitter/X** - Social media integration for posting and reading tweets.

- **Whoop** - Health and fitness data integration for accessing workout and recovery metrics.

### Speech-to-Text Improvements

- Upgraded to **Deepgram Nova-3** (20251210) - the latest model for improved transcription accuracy.
- Added **custom vocabulary support** for better recognition of domain-specific terms.
- Replaced FAL WhisperX with Deepgram pre-recorded transcription for cost optimization.
- Language detection and translation optimizations for multilingual support.

### Chat Tools System

Apps can now define "Chat Tools" - custom functions that extend the AI's capabilities. This allows third-party apps to expose their functionality directly in conversations.

### Meeting Detection

Automatic meeting detection for desktop sources. When a meeting is detected, context is passed to the conversation for better summarization and action item extraction.

### Starred Conversations

Users can now star important conversations to keep them easily accessible. Starred conversations appear in a dedicated filter and are preserved for quick reference.

### Conversation Merging

Ability to merge related conversations together, with automatic reprocessing of discarded conversations after transcript merge.

### Admin Capabilities

- New endpoint to retrieve all apps (approved and unapproved) for admin review.
- App ranking algorithm for search results based on install count and ratings.

### Infrastructure

- **Sentry Integration** - Error tracking with configurable sample rates and an `SENTRY_ENABLED` flag for local development.
- **White-label Support** - `APP_NAME` configuration for custom branding.
- **Local Docker Development** - New `docker-compose` setup in `/backend/infra/local/` for running the backend locally.
- **Hosted MCP Server** - Model Context Protocol support for enhanced AI capabilities.
- Migrated Pusher to GKE for improved scalability.

### Reliability Improvements

- Orphaned conversation cleanup with timeout checks.
- Notification deduplication to prevent spam.
- Improved Pusher triggering during conversation processing.
- Rate limiting for persona updates (1 per day).

---

## Web Admin (Frontend)

### Apps Review & Management

A new comprehensive admin interface for managing apps in the marketplace:

- **Review Queue** - View all pending apps awaiting approval with detailed information.
- **Approval Workflow** - Approve or reject apps with a single click.
- **App Details** - View app metadata, descriptions, capabilities, and installation statistics.
- **Filtering & Search** - Find apps by name, category, or approval status.

### Dashboard Enhancements

- **Conversation Categories Chart** - Visual breakdown of conversation topics across all users.
- **Analytics Dashboard** - Usage metrics and platform statistics.
- **Users Management** - Admin tools for user account management.

### API Routes

New admin API endpoints for:
- Fetching all apps (approved + pending)
- Approving/rejecting individual apps
- User management operations

---

## Flutter App

### Generative UI Widgets

The conversation detail view now supports rich, interactive content:

- **Tables** - Structured data displayed in formatted tables with headers and rows.
- **Highlights** - Key information emphasized with colored backgrounds and styling.
- **Pie Charts** - Visual data representation for statistics and breakdowns.
- **Enhanced Markdown** - Improved markdown rendering with better typography.

### New Typography

Added **Geist font family** (Regular, Medium, SemiBold, Bold) for a modern, clean interface.

### Starred Conversations

Star your most important conversations for quick access. A star icon appears in the conversation detail view, and starred items can be filtered in the conversation list.

### Compact Conversation List

New compact view option for the conversation list, showing more conversations at a glance with essential information.

### Build Configuration

Multi-environment support with separate configurations:
- **Dev flavor** - For development and testing
- **Prod flavor** - For production releases
- iOS and macOS xcconfig files for each environment

### Developer Settings

Enhanced developer options for debugging and testing, including auth token logging for local development.

---

## Migration Notes

### For Local Development

1. Backend now requires Docker Compose - see `/backend/infra/local/` for setup.
2. Set `SENTRY_ENABLED=false` in `.env` to prevent errors being sent during development.
3. Use `--flavor dev` when running the Flutter app locally.

### Breaking Changes

- Conversation date filtering logic moved to backend.
- Calendar integrations renamed to generic "integrations" system.
- Some deprecated endpoints removed (e.g., `delete_limitless_conversations`).

---

## Summary

| Area | Key Changes |
|------|-------------|
| **Backend** | New integrations (Calendar, GitHub, Gmail, Notion, Twitter, Whoop), Deepgram Nova-3, Chat Tools, Meeting Detection, Starred Conversations |
| **Web Admin** | Apps review system, conversation analytics, user management |
| **Flutter App** | Generative UI widgets, Geist fonts, starred conversations, compact list view, multi-flavor builds |