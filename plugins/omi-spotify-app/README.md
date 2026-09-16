# Spotify Integration for Omi

Control your Spotify music with voice commands through your Omi device. Search songs, manage playlists, control playback, and discover new music – all hands-free!

![Spotify + Omi](https://storage.googleapis.com/pr-newsroom-wp/1/2018/11/Spotify_Logo_RGB_Green.png)

---

## Features

- Search Songs - Find any song, artist, or album instantly with voice
- Playlist Management - Add songs to playlists and create new playlists
- Playback Control - Play, pause, skip, and control your music
- Now Playing - Check what's currently playing
- Recommendations - Get personalized song recommendations
- Secure OAuth - Industry-standard Spotify OAuth 2.0 authentication

---

## Quick Start

1. Install the Spotify app from the Omi App Store
2. Click "Connect with Spotify" to authenticate
3. (Optional) Set a default playlist for quick song additions
4. Start using voice commands!

---

## Spotify Developer Setup

### Spotify App Credentials

| Field             | Value |
| ----------------- | ----- |
| **Client ID**     | *(set via `SPOTIFY_CLIENT_ID` env)* |
| **Client Secret** | *(set via `SPOTIFY_CLIENT_SECRET` env)* |

Never commit real client secrets. Configure them via environment variables only.

### Environment Variables

```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=https://your-domain.com/auth/spotify/callback
PORT=8080
REDIS_URL=  # Optional: for production use
```

### Local Setup

```bash
cd plugins/omi-spotify-app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python main.py
```

### Deploy notes

Set `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, and `SPOTIFY_REDIRECT_URI` in your host (e.g. Railway Variables). Do not put secrets in the repository or README.

## License

MIT License - feel free to modify and distribute.
