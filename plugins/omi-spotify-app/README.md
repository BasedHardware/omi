# Spotify Integration for Omi

Control your Spotify music with voice commands through your Omi device. Search songs, manage playlists, control playback, and discover new music – all hands-free!

![Spotify + Omi](https://storage.googleapis.com/pr-newsroom-wp/1/2018/11/Spotify_Logo_RGB_Green.png)

---

## 🎵 Features

- **🔍 Search Songs** - Find any song, artist, or album instantly with voice
- **📝 Playlist Management** - Add songs to playlists and create new playlists
- **▶️ Playback Control** - Play, pause, skip, and control your music
- **🎧 Now Playing** - Check what's currently playing
- **💡 Recommendations** - Get personalized song recommendations
- **🔐 Secure OAuth** - Industry-standard Spotify OAuth 2.0 authentication

---

## 🚀 Quick Start

1. Install the Spotify app from the Omi App Store
2. Click "Connect with Spotify" to authenticate
3. (Optional) Set a default playlist for quick song additions
4. Start using voice commands!

---

## 🗣️ Voice Commands

| Command                                      | Description                   |
| -------------------------------------------- | ----------------------------- |
| "Search for Shape of You"                    | Find songs by name            |
| "Search for songs by Ed Sheeran"             | Find songs by artist          |
| "Add Blinding Lights to my workout playlist" | Add song to specific playlist |
| "Add this song to my playlist"               | Add to default playlist       |
| "Play Bohemian Rhapsody"                     | Start playing a song          |
| "Skip this song"                             | Skip to next track            |
| "Pause" / "Resume"                           | Control playback              |
| "What's playing?"                            | See current track             |
| "Create a playlist called Road Trip"         | Create new playlist           |
| "Show my playlists"                          | List your playlists           |
| "Get song recommendations"                   | Discover new music            |

---

## 📋 Omi App Store Details

### App Information

| Field           | Value                                                                                                                                                              |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **App Name**    | Spotify                                                                                                                                                            |
| **Category**    | Music & Entertainment                                                                                                                                              |
| **Description** | Control your Spotify music with voice commands. Search songs, manage playlists, control playback, and discover new music – all hands-free through your Omi device. |
| **Author**      | Omi Community                                                                                                                                                      |
| **Version**     | 1.0.0                                                                                                                                                              |

### Capabilities

- ✅ **External Integration** (required for chat tools)
- ✅ **Chat** (for voice command responses)

### URLs

| URL Type                    | URL                                                                                 |
| --------------------------- | ----------------------------------------------------------------------------------- |
| **App Home URL**            | `https://spacious-undiscouragingly-kelle.ngrok-free.dev/`                           |
| **Setup Completed URL**     | `https://spacious-undiscouragingly-kelle.ngrok-free.dev/setup/spotify`              |
| **Chat Tools Manifest URL** | `https://spacious-undiscouragingly-kelle.ngrok-free.dev/.well-known/omi-tools.json` |

> **Important:** Omi automatically appends `?uid=USER_ID` to these URLs. Do NOT include `{uid}` in the URL.

### Spotify Redirect URI (Add to Spotify Dashboard)

```
https://spacious-undiscouragingly-kelle.ngrok-free.dev/auth/spotify/callback
```

---

## 🔧 Chat Tools

This app exposes a manifest endpoint at `/.well-known/omi-tools.json` that Omi automatically fetches when the app is created or updated.

The **Chat Tools Manifest URL** is:

```
https://spacious-undiscouragingly-kelle.ngrok-free.dev/.well-known/omi-tools.json
```

The manifest includes all 8 tools with their complete parameter schemas, so the AI can properly extract parameters from user requests.

### Available Tools

| Tool                  | Description                           |
| --------------------- | ------------------------------------- |
| `search_songs`        | Search for songs on Spotify           |
| `add_to_playlist`     | Add a song to a Spotify playlist      |
| `create_playlist`     | Create a new Spotify playlist         |
| `get_playlists`       | Get the user's Spotify playlists      |
| `get_now_playing`     | Get the currently playing track       |
| `control_playback`    | Control playback (play/pause/skip)    |
| `play_song`           | Search for and play a specific song   |
| `get_recommendations` | Get personalized song recommendations |

---

## 🔐 Spotify Developer Setup

### Required Spotify Scopes

The app requests these Spotify permissions:

- `user-read-private` - Read user's subscription details
- `user-read-email` - Read user's email
- `playlist-read-private` - Read private playlists
- `playlist-read-collaborative` - Read collaborative playlists
- `playlist-modify-public` - Create/edit public playlists
- `playlist-modify-private` - Create/edit private playlists
- `user-library-read` - Read saved tracks
- `user-library-modify` - Save/remove tracks
- `user-read-playback-state` - Read playback state
- `user-modify-playback-state` - Control playback
- `user-read-currently-playing` - Read currently playing
- `user-read-recently-played` - Read recently played

### Spotify App Credentials

| Field             | Value                              |
| ----------------- | ---------------------------------- |
| **Client ID**     | `96f6f46db00a480eb1ced59ea90bf2f4` |
| **Client Secret** | `9ca3f5cfe6b6444a80c09aa3e59f4d83` |

### Redirect URI to Add in Spotify Dashboard

Add this redirect URI to your Spotify app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard):

```
https://spacious-undiscouragingly-kelle.ngrok-free.dev/auth/spotify/callback
```

---

## 🛠️ Development

### Prerequisites

- Python 3.8+
- Spotify Developer Account

### Local Setup

```bash
# Navigate to the plugin directory
cd plugins/spotify

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file and configure
cp .env.example .env
# Edit .env with your credentials

# Run the server
python main.py
```

### Environment Variables

```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=https://your-domain.com/auth/spotify/callback
PORT=8080
REDIS_URL=  # Optional: for production use
```

---

## 🚀 Deploy to Railway

### Step 1: Create Railway Project

1. Go to [Railway](https://railway.app) and sign in
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repository and choose the `plugins/spotify` folder

### Step 2: Add Redis Database

1. In your Railway project, click **"+ New"** → **"Database"** → **"Add Redis"**
2. Railway automatically creates and connects the Redis instance
3. The `REDIS_URL` environment variable is set automatically

### Step 3: Configure Environment Variables

Go to your service's **Variables** tab and add:

| Variable                | Value                                                   |
| ----------------------- | ------------------------------------------------------- |
| `SPOTIFY_CLIENT_ID`     | `96f6f46db00a480eb1ced59ea90bf2f4`                      |
| `SPOTIFY_CLIENT_SECRET` | `9ca3f5cfe6b6444a80c09aa3e59f4d83`                      |
| `SPOTIFY_REDIRECT_URI`  | `https://YOUR-APP.up.railway.app/auth/spotify/callback` |

> **Note:** Replace `YOUR-APP` with your actual Railway app domain (shown in Settings → Domains)

### Step 4: Configure Root Directory

If deploying from the main repo, set the **Root Directory** to `plugins/spotify`:

1. Go to **Settings** → **Build** → **Root Directory**
2. Enter: `plugins/spotify`

### Step 5: Update Spotify Dashboard

Add your Railway URL as a redirect URI in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard):

```
https://YOUR-APP.up.railway.app/auth/spotify/callback
```

### Step 6: Update Omi App Store

Update your app URLs in the Omi App Store:

| URL Type                    | Value                                                        |
| --------------------------- | ------------------------------------------------------------ |
| **App Home URL**            | `https://YOUR-APP.up.railway.app/`                           |
| **Setup Completed URL**     | `https://YOUR-APP.up.railway.app/setup/spotify`              |
| **Chat Tools Manifest URL** | `https://YOUR-APP.up.railway.app/.well-known/omi-tools.json` |

### Railway Architecture

```
┌─────────────────────────────────────────────────┐
│                 Railway Project                  │
├─────────────────────────────────────────────────┤
│  ┌───────────────┐     ┌───────────────────┐   │
│  │  Spotify App  │────▶│  Redis Database   │   │
│  │  (FastAPI)    │     │  (Persistent)     │   │
│  │               │     │                   │   │
│  │  - OAuth      │     │  - User tokens    │   │
│  │  - Chat tools │     │  - Settings       │   │
│  │  - API proxy  │     │  - Playlists      │   │
│  └───────────────┘     └───────────────────┘   │
│         │                                       │
│         ▼                                       │
│  https://YOUR-APP.up.railway.app               │
└─────────────────────────────────────────────────┘
```

### API Endpoints

| Endpoint                     | Method | Description                    |
| ---------------------------- | ------ | ------------------------------ |
| `/`                          | GET    | Home page / App settings       |
| `/health`                    | GET    | Health check                   |
| `/auth/spotify`              | GET    | Start OAuth flow               |
| `/auth/spotify/callback`     | GET    | OAuth callback                 |
| `/setup/spotify`             | GET    | Check setup status             |
| `/disconnect`                | GET    | Disconnect account             |
| `/tools/search_songs`        | POST   | Chat tool: Search songs        |
| `/tools/add_to_playlist`     | POST   | Chat tool: Add to playlist     |
| `/tools/create_playlist`     | POST   | Chat tool: Create playlist     |
| `/tools/get_playlists`       | POST   | Chat tool: Get playlists       |
| `/tools/get_now_playing`     | POST   | Chat tool: Get now playing     |
| `/tools/control_playback`    | POST   | Chat tool: Control playback    |
| `/tools/play_song`           | POST   | Chat tool: Play song           |
| `/tools/get_recommendations` | POST   | Chat tool: Get recommendations |

---

## 🐛 Troubleshooting

### "User not authenticated"

- Complete the Spotify OAuth flow by clicking "Connect with Spotify" in app settings

### "No active device found"

- Open Spotify on your phone, computer, or smart speaker before using playback controls

### "Could not find playlist"

- Check playlist name pronunciation
- Try setting a default playlist in app settings
- Use "Show my playlists" to see available playlists

### "Could not find song"

- Try including the artist name: "Add Shape of You by Ed Sheeran"
- Use simpler search terms

---

## 📄 License

MIT License - feel free to modify and distribute.

---

## 🤝 Support

For issues or feature requests, please open an issue on GitHub or contact the Omi community.

---

Made with ❤️ for Omi
