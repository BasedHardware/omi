# OMI + Microsoft 365 Integration

Seamlessly connect your OMI wearable with Microsoft 365 — Outlook Mail,
Calendar, Teams, SharePoint and OneDrive — with a single sign-in.

## Features

- Draft, search and send Outlook mail
- List upcoming events, create meetings and find free slots in your calendar
- Send Teams chat messages and create Teams online meetings
- Browse recent files across OneDrive and SharePoint, upload text content,
  read documents
- Secure OAuth 2.0 authentication via Microsoft Entra ID (multi-tenant —
  works for any personal `@outlook.com` / `@hotmail.com` account and any
  Microsoft 365 work or school account)
- Tokens are stored server-side; you can revoke access at any time

## Setup

1. Open **Apps** in OMI and find **Microsoft 365**.
2. Tap **Connect with Microsoft**.
3. Sign in with your Microsoft account and approve the requested
   permissions.
4. You will be redirected back to OMI automatically. That's it.

## Permissions Requested

The plugin requests the minimum delegated Microsoft Graph scopes required
for the features above: `User.Read`, `MailboxSettings.Read`, `Mail.Read`,
`Mail.Send`, `Mail.ReadWrite`, `Calendars.ReadWrite`, `Chat.ReadWrite`,
`ChannelMessage.Send`, `OnlineMeetings.ReadWrite`, `Team.ReadBasic.All`,
`Files.ReadWrite.All`, `Sites.Read.All`, `People.Read`, `Contacts.Read`,
`offline_access`.

## Revoke Access

You can disconnect at any time from the OMI app. You may also revoke the
consent from the Microsoft side at
<https://myaccount.microsoft.com/> → **Privacy** → **Apps and services
you've authorized**.

## Source & Issues

- Source: https://github.com/snyfer/omi-ms365-plugin
- Backend: https://omi-ms365-plugin.onrender.com
- Manifest: https://omi-ms365-plugin.onrender.com/.well-known/omi-tools.json
- Questions / issues: please open an issue on the GitHub repo above.
