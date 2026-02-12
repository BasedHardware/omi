from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import os
from dotenv import load_dotenv
from typing import List, Dict, Any

# Fix for Railway/production: Allow OAuth over HTTP (Railway handles HTTPS at proxy)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from simple_storage import SimpleUserStorage, SimpleSessionStorage, OAuthStateStorage, users, save_users
from twitter_client import TwitterClient
from tweet_detector import TweetDetector

load_dotenv()

# Initialize services
twitter_client = TwitterClient()
tweet_detector = TweetDetector()

app = FastAPI(
    title="OMI Twitter Integration",
    description="Real-time Twitter posting via OMI voice commands",
    version="1.0.0"
)


@app.get("/")
async def root(uid: str = Query(None)):
    """Root endpoint with setup instructions."""
    # If uid provided, show personalized setup page
    if uid:
        auth_url = f"/auth?uid={uid}"
        return HTMLResponse(content=f"""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background: linear-gradient(135deg, #1DA1F2 0%, #0d8bd9 100%);
                        min-height: 100vh;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        background: white;
                        border-radius: 16px;
                        padding: 30px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    }}
                    h1 {{
                        color: #1DA1F2;
                        margin-top: 0;
                        font-size: 28px;
                    }}
                    .icon {{
                        font-size: 48px;
                        margin-bottom: 20px;
                    }}
                    .step {{
                        background: #f8f9fa;
                        padding: 15px;
                        border-radius: 8px;
                        margin: 15px 0;
                        border-left: 4px solid #1DA1F2;
                    }}
                    .step h3 {{
                        margin-top: 0;
                        color: #1DA1F2;
                        font-size: 16px;
                    }}
                    .example {{
                        background: #e8f5fe;
                        padding: 10px;
                        border-radius: 6px;
                        margin: 10px 0;
                        font-style: italic;
                    }}
                    .btn {{
                        display: inline-block;
                        background: #1DA1F2;
                        color: white;
                        padding: 15px 30px;
                        border-radius: 30px;
                        text-decoration: none;
                        font-weight: bold;
                        margin: 20px 0;
                        transition: background 0.3s;
                    }}
                    .btn:hover {{
                        background: #0d8bd9;
                    }}
                    ul {{
                        line-height: 1.8;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">🐦✨</div>
                    <h1>Twitter Voice Poster</h1>
                    <p>Tweet with your voice using OMI!</p>
                    
                    <a href="{auth_url}" class="btn">🔐 Connect Twitter Account</a>
                    
                    <div class="step">
                        <h3>📱 How to Use</h3>
                        <p>After connecting your Twitter account:</p>
                        <ol>
                            <li>Say <strong>"Tweet Now"</strong> to your OMI device</li>
                            <li>Speak your tweet naturally</li>
                            <li>AI automatically detects when you're done</li>
                            <li>Your tweet is posted instantly! 🚀</li>
                        </ol>
                    </div>
                    
                    <div class="step">
                        <h3>💬 Examples</h3>
                        <div class="example">
                            "Tweet Now, Just had an amazing conversation about AI and creativity!"
                        </div>
                        <div class="example">
                            "Tweet Now, Beautiful sunset today. This is incredible. End tweet."
                        </div>
                        <div class="example">
                            "Post Tweet, Excited to share my new project with the world!"
                        </div>
                    </div>
                    
                    <div class="step">
                        <h3>🎯 Trigger Phrases</h3>
                        <ul>
                            <li>"Tweet Now"</li>
                            <li>"Post Tweet"</li>
                            <li>"Send Tweet"</li>
                            <li>"Tweet This"</li>
                        </ul>
                    </div>
                    
                    <div class="step">
                        <h3>💡 Pro Tips</h3>
                        <ul>
                            <li>Speak naturally - AI cleans up filler words</li>
                            <li>Say "End tweet" to finish explicitly</li>
                            <li>Natural pauses are detected automatically</li>
                            <li>Works best with 1-2 sentence tweets</li>
                        </ul>
                    </div>
                    
                    <p style="text-align: center; color: #666; margin-top: 30px;">
                        Made with ❤️ for the OMI community
                    </p>
                </div>
            </body>
        </html>
        """)
    
    # Default API info
    return {
        "app": "OMI Twitter Integration",
        "version": "1.0.0",
        "status": "active",
        "storage": "in-memory (simple mode)",
        "endpoints": {
            "auth": "/auth?uid=<user_id>",
            "webhook": "/webhook?session_id=<session>&uid=<user_id>",
            "setup_check": "/setup-completed?uid=<user_id>"
        }
    }


@app.get("/auth")
async def auth_start(uid: str = Query(..., description="User ID from OMI")):
    """Start OAuth flow for Twitter authentication."""
    redirect_uri = os.getenv("OAUTH_REDIRECT_URL", "http://localhost:8000/auth/callback")
    
    try:
        # Get authorization URL (Tweepy generates its own state parameter)
        # We store the mapping between Tweepy's state and our uid internally
        auth_url = twitter_client.get_authorization_url(redirect_uri, uid)
        
        # Don't modify the URL - Tweepy's state parameter is already included
        return RedirectResponse(url=auth_url)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"OAuth initialization failed: {str(e)}")


@app.get("/auth/callback")
async def auth_callback(
    request: Request,
    state: str = Query(None),
    code: str = Query(None)
):
    """Handle OAuth callback from Twitter."""
    if not code:
        return HTMLResponse(
            content="""
            <html>
                <body style="font-family: Arial; padding: 40px; text-align: center;">
                    <h2>❌ Authentication Failed</h2>
                    <p>Authorization code not received. Please try again.</p>
                </body>
            </html>
            """,
            status_code=400
        )
    
    # state is Tweepy's generated state parameter
    
    try:
        # Exchange code for access token using stored OAuth handler
        # This also retrieves the uid we associated with this state
        full_url = str(request.url)
        token_data, uid = twitter_client.get_access_token(full_url, state)
        
        # Save user tokens with expiration info
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 7200)
        
        print(f"🔑 Token data received:", flush=True)
        print(f"   Access token: {access_token[:20]}..." if access_token else "   Access token: None", flush=True)
        print(f"   Refresh token: {refresh_token[:20]}..." if refresh_token else "   Refresh token: None", flush=True)
        print(f"   Expires in: {expires_in}s ({expires_in/3600:.1f}h)", flush=True)
        
        SimpleUserStorage.save_user(
            uid=uid,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in
        )
        
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
                    <title>Twitter • Account Connected</title>
                    <style>
                        * {
                            margin: 0;
                            padding: 0;
                            box-sizing: border-box;
                        }
                        
                        body {
                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                            background: #FFFFFF;
                            min-height: 100vh;
                            display: flex;
                            flex-direction: column;
                        }
                        
                        .header {
                            padding: 16px 20px;
                            border-bottom: 1px solid #EFF3F4;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        }
                        
                        .twitter-logo {
                            width: 32px;
                            height: 32px;
                            fill: #1D9BF0;
                        }
                        
                        .container {
                            flex: 1;
                            max-width: 600px;
                            width: 100%;
                            margin: 0 auto;
                            padding: 32px 20px;
                        }
                        
                        .success-card {
                            background: #FFFFFF;
                            border: 1px solid #EFF3F4;
                            border-radius: 16px;
                            padding: 32px 24px;
                            text-align: center;
                            margin-bottom: 16px;
                        }
                        
                        .check-icon {
                            width: 64px;
                            height: 64px;
                            background: #00BA7C;
                            border-radius: 50%;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            margin: 0 auto 20px;
                        }
                        
                        .check-icon svg {
                            width: 32px;
                            height: 32px;
                            stroke: white;
                            fill: none;
                            stroke-width: 3;
                        }
                        
                        h1 {
                            font-size: 31px;
                            font-weight: 800;
                            color: #0F1419;
                            margin-bottom: 8px;
                            line-height: 1.2;
                        }
                        
                        .subtitle {
                            font-size: 17px;
                            color: #536471;
                            margin-bottom: 20px;
                            font-weight: 400;
                        }
                        
                        .info-card {
                            background: #FFFFFF;
                            border: 1px solid #EFF3F4;
                            border-radius: 16px;
                            padding: 20px;
                            text-align: left;
                            margin-bottom: 16px;
                        }
                        
                        .info-title {
                            font-size: 20px;
                            font-weight: 700;
                            color: #0F1419;
                            margin-bottom: 16px;
                        }
                        
                        .step {
                            display: flex;
                            gap: 12px;
                            margin-bottom: 16px;
                            padding-bottom: 16px;
                            border-bottom: 1px solid #EFF3F4;
                        }
                        
                        .step:last-child {
                            border-bottom: none;
                            margin-bottom: 0;
                            padding-bottom: 0;
                        }
                        
                        .step-icon {
                            font-size: 24px;
                            flex-shrink: 0;
                        }
                        
                        .step-content {
                            flex: 1;
                        }
                        
                        .step-text {
                            color: #0F1419;
                            font-size: 15px;
                            line-height: 1.5;
                            font-weight: 400;
                        }
                        
                        .step-text strong {
                            font-weight: 700;
                            color: #1D9BF0;
                        }
                        
                        .example-card {
                            background: #F7F9F9;
                            border: 1px solid #EFF3F4;
                            border-radius: 16px;
                            padding: 20px;
                            margin-bottom: 16px;
                        }
                        
                        .example-label {
                            font-size: 13px;
                            font-weight: 700;
                            color: #536471;
                            margin-bottom: 12px;
                            text-transform: uppercase;
                            letter-spacing: 0.5px;
                        }
                        
                        .tweet-example {
                            background: white;
                            border: 1px solid #CFD9DE;
                            border-radius: 12px;
                            padding: 16px;
                        }
                        
                        .tweet-text {
                            color: #0F1419;
                            font-size: 15px;
                            line-height: 1.5;
                        }
                        
                        .tweet-meta {
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            margin-top: 12px;
                            font-size: 13px;
                            color: #536471;
                        }
                        
                        .divider {
                            height: 1px;
                            background: #EFF3F4;
                            margin: 24px 0;
                        }
                        
                        .footer {
                            text-align: center;
                            padding: 20px;
                            font-size: 13px;
                            color: #536471;
                        }
                        
                        .footer a {
                            color: #1D9BF0;
                            text-decoration: none;
                        }
                        
                        @media (max-width: 600px) {
                            .container {
                                padding: 24px 16px;
                            }
                            
                            .success-card,
                            .info-card,
                            .example-card {
                                padding: 24px 16px;
                            }
                            
                            h1 {
                                font-size: 27px;
                            }
                            
                            .subtitle {
                                font-size: 15px;
                            }
                        }
                    </style>
                </head>
                <body>
                    <div class="header">
                        <svg class="twitter-logo" viewBox="0 0 24 24" aria-hidden="true">
                            <g><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"></path></g>
                        </svg>
                    </div>
                    
                    <div class="container">
                        <div class="success-card">
                            <div class="check-icon">
                                <svg viewBox="0 0 24 24">
                                    <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                            </div>
                            <h1>You're connected!</h1>
                        </div>
                        
                        <div class="info-card">
                            <div class="info-title">How to use</div>
                            
                            <div class="step">
                                <div class="step-icon">🎤</div>
                                <div class="step-content">
                                    <div class="step-text">Say <strong>"Tweet Now"</strong> to your OMI device</div>
                                </div>
                            </div>
                            
                            <div class="step">
                                <div class="step-icon">💬</div>
                                <div class="step-content">
                                    <div class="step-text">Speak your message naturally</div>
                                </div>
                            </div>
                            
                            <div class="step">
                                <div class="step-icon">✨</div>
                                <div class="step-content">
                                    <div class="step-text">AI cleans up your speech and posts it</div>
                                </div>
                            </div>
                            
                            <div class="step">
                                <div class="step-icon">📲</div>
                                <div class="step-content">
                                    <div class="step-text">Get notified when your tweet is live!</div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="example-card">
                            <div class="example-label">Try saying</div>
                            <div class="tweet-example">
                                <div class="tweet-text">Tweet Now, I just had an incredible idea about voice-first social media!</div>
                                <div class="tweet-meta">
                                    <span>🤖</span>
                                    <span>AI will clean and post this automatically</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="footer">
                        <p>Powered by <a href="https://omi.me" target="_blank">OMI</a> • Made with ❤️</p>
                    </div>
                </body>
            </html>
            """
        )
    
    except Exception as e:
        error_uid = state if state else "unknown"
        return HTMLResponse(
            content=f"""
            <html>
                <body style="font-family: Arial; padding: 40px; text-align: center;">
                    <h2>❌ Authentication Error</h2>
                    <p>Failed to complete authentication: {str(e)}</p>
                    <p><a href="/auth?uid={error_uid}">Try again</a></p>
                </body>
            </html>
            """,
            status_code=500
        )


@app.get("/setup-completed")
async def check_setup(uid: str = Query(..., description="User ID from OMI")):
    """Check if user has completed setup (authenticated with Twitter)."""
    is_setup = SimpleUserStorage.is_authenticated(uid)
    return {"is_setup_completed": is_setup}


@app.post("/webhook")
async def webhook(
    request: Request,
    uid: str = Query(..., description="User ID from OMI"),
    session_id: str = Query(None, description="Session ID from OMI (optional)"),
    sample_rate: int = Query(None, description="Sample rate (optional, for audio streams)")
):
    """
    Real-time transcript webhook endpoint.
    Handles requests with or without session_id parameter.
    """
    # Use consistent session_id per user (no timestamp!)
    # This ensures session persists across all segments
    if not session_id:
        session_id = f"omi_session_{uid}"
    
    # Get user
    user = SimpleUserStorage.get_user(uid)
    
    if not user or not user.get("access_token"):
        return JSONResponse(
            content={
                "message": "User not authenticated. Please complete setup first.",
                "setup_required": True
            },
            status_code=401
        )
    
    # Check if token needs refresh
    if SimpleUserStorage.is_token_expired(uid):
        print(f"🔄 Token expired for user {uid[:10]}...", flush=True)
        
        # Check if we have a valid refresh token
        refresh_token = user.get("refresh_token")
        
        if not refresh_token or refresh_token == "null":
            print(f"⚠️  No refresh token! User must re-authenticate with offline.access scope.", flush=True)
            return JSONResponse(
                content={
                    "message": "🔄 Your session expired. Please re-authenticate in the OMI app to continue tweeting.",
                    "setup_required": True
                },
                status_code=401
            )
        
        # Try to refresh
        try:
            print(f"🔄 Refreshing token...", flush=True)
            new_token_data = twitter_client.refresh_access_token(refresh_token)
            
            # Save new tokens
            SimpleUserStorage.save_user(
                uid=uid,
                access_token=new_token_data.get("access_token"),
                refresh_token=new_token_data.get("refresh_token", refresh_token),
                expires_in=new_token_data.get("expires_in", 7200)
            )
            
            # Update user reference
            user = SimpleUserStorage.get_user(uid)
            print(f"✅ Token refreshed!", flush=True)
            
        except Exception as e:
            print(f"❌ Refresh error: {e}", flush=True)
            # Delete old invalid token
            del users[uid]
            save_users()
            return JSONResponse(
                content={
                    "message": "🔄 Session expired. Please re-authenticate in the OMI app.",
                    "setup_required": True
                },
                status_code=401
            )
    
    # Parse payload from OMI
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    
    # Handle both formats:
    # 1. Direct list: [{"text": "...", ...}, ...]
    # 2. Dict with segments: {"session_id": "...", "segments": [...]}
    segments = []
    if isinstance(payload, dict):
        # Extract segments from dict
        segments = payload.get("segments", [])
        # Use session_id from payload if not in query params
        if not session_id and "session_id" in payload:
            session_id = payload["session_id"]
    elif isinstance(payload, list):
        # Direct list of segments
        segments = payload
    
    # Log what we received for debugging
    print(f"📥 Received {len(segments) if segments else 0} segment(s) from OMI", flush=True)
    if segments:
        for i, seg in enumerate(segments[:3]):  # Show first 3
            text = seg.get('text', 'NO TEXT') if isinstance(seg, dict) else str(seg)
            print(f"   Segment {i}: {text[:100]}", flush=True)
    
    if not segments or not isinstance(segments, list):
        # Silent response for empty/invalid data
        return {"status": "ok"}
    
    # Ensure we have a consistent session_id per user
    # Use uid as session_id so it persists across calls
    if not session_id:
        session_id = f"omi_session_{uid}"
    
    # Get or create session
    session = SimpleSessionStorage.get_or_create_session(session_id, uid)
    
    # Debug: show current session state
    print(f"📊 Session state: mode={session.get('tweet_mode')}, count={session.get('segments_count', 0)}", flush=True)
    
    # Process segments
    response_message = await process_segments(session, segments, user)
    
    # Only send notifications for final tweet post (success or failure)
    # Silent responses during collection so user doesn't get spammed
    if response_message and ("✅ Tweet posted:" in response_message or "❌ Failed:" in response_message):
        print(f"✉️  USER NOTIFICATION: {response_message}", flush=True)
        return {
            "message": response_message,
            "session_id": session_id,
            "processed_segments": len(segments)
        }
    
    # Silent response for everything else (listening, collecting, etc.)
    print(f"🔇 Silent response: {response_message}", flush=True)
    return {"status": "ok"}


async def process_segments(
    session: dict,
    segments: List[Dict[str, Any]],
    user: dict
) -> str:
    """
    ALWAYS collect exactly 3 segments after 'Tweet Now', then AI extracts the tweet.
    - Segment 1: Contains "Tweet Now" + start of tweet
    - Segment 2: Middle part (auto-collected)
    - Segment 3: End part (auto-collected)
    - AI decides what's actually the tweet and cleans it
    """
    
    # Extract text from segments
    segment_texts = [seg.get("text", "") for seg in segments]
    full_text = " ".join(segment_texts)
    
    session_id = session["session_id"]
    
    print(f"🔍 Received: '{full_text}'", flush=True)
    print(f"📊 Session mode: {session['tweet_mode']}, Count: {session.get('segments_count', 0)}/3", flush=True)
    
    # Check for trigger phrase
    if tweet_detector.detect_trigger(full_text):
        tweet_content = tweet_detector.extract_tweet_content(full_text)
        
        print(f"🎤 TRIGGER! Starting 3-segment collection...", flush=True)
        print(f"   Segment 1 content: '{tweet_content}'", flush=True)
        
        # Start collecting - ALWAYS wait for 2 more segments
        SimpleSessionStorage.update_session(
            session_id,
            tweet_mode="recording",
            accumulated_text=tweet_content,
            segments_count=1
        )
        
        # Silent - don't notify user yet
        return "collecting_1"
    
    # If in recording mode, collect more segments
    elif session["tweet_mode"] == "recording":
        accumulated = session.get("accumulated_text", "")
        segments_count = session.get("segments_count", 0)
        
        # Add this segment
        accumulated += " " + full_text
        segments_count += 1
        
        print(f"📝 Segment {segments_count}/3: '{full_text}'", flush=True)
        print(f"📚 Full accumulated: '{accumulated[:150]}...'", flush=True)
        
        # Always collect 3 segments
        if segments_count >= 3:
            print(f"✅ Got all 3 segments! Sending to AI...", flush=True)
            
            # AI extracts the actual tweet from all 3 segments
            cleaned_content = await tweet_detector.ai_extract_tweet_from_segments(accumulated)
            
            print(f"✨ AI extracted tweet: '{cleaned_content}'", flush=True)
            
            if len(cleaned_content.strip()) > 3:
                print(f"📤 Posting to Twitter...", flush=True)
                result = await twitter_client.post_tweet(user["access_token"], cleaned_content)
                
                if result and result.get("success"):
                    SimpleSessionStorage.reset_session(session_id)
                    print(f"🎉 SUCCESS! Tweet ID: {result.get('tweet_id')}", flush=True)
                    return f"✅ Tweet posted: '{cleaned_content}'"
                else:
                    error = result.get("error", "Unknown") if result else "Failed"
                    SimpleSessionStorage.reset_session(session_id)
                    print(f"❌ FAILED: {error}", flush=True)
                    return f"❌ Failed: {error}"
            else:
                SimpleSessionStorage.reset_session(session_id)
                print(f"⚠️  AI returned empty tweet", flush=True)
                return "❌ No valid tweet content"
        else:
            # Still collecting (need segment 2 or 3)
            SimpleSessionStorage.update_session(
                session_id,
                accumulated_text=accumulated,
                segments_count=segments_count
            )
            # Silent - don't notify user yet
            return f"collecting_{segments_count}"
    
    # Passive listening - silent
    return "listening"


@app.get("/test")
async def test_interface():
    """Web interface for testing tweet functionality."""
    return HTMLResponse(content="""
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Twitter Voice Poster - Test Interface</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: #f5f8fa;
                }
                .container {
                    max-width: 800px;
                    margin: 0 auto;
                }
                .header {
                    background: linear-gradient(135deg, #1DA1F2 0%, #0d8bd9 100%);
                    color: white;
                    padding: 30px;
                    border-radius: 12px;
                    margin-bottom: 20px;
                }
                .card {
                    background: white;
                    border-radius: 12px;
                    padding: 25px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }
                .input-group {
                    margin-bottom: 15px;
                }
                label {
                    display: block;
                    margin-bottom: 8px;
                    font-weight: 600;
                    color: #14171a;
                }
                input[type="text"], textarea {
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #e1e8ed;
                    border-radius: 8px;
                    font-size: 16px;
                    box-sizing: border-box;
                    font-family: inherit;
                }
                input[type="text"]:focus, textarea:focus {
                    outline: none;
                    border-color: #1DA1F2;
                }
                textarea {
                    min-height: 100px;
                    resize: vertical;
                }
                .btn {
                    background: #1DA1F2;
                    color: white;
                    padding: 12px 24px;
                    border: none;
                    border-radius: 30px;
                    font-size: 16px;
                    font-weight: bold;
                    cursor: pointer;
                    margin-right: 10px;
                    transition: background 0.3s;
                }
                .btn:hover {
                    background: #0d8bd9;
                }
                .btn:disabled {
                    background: #aab8c2;
                    cursor: not-allowed;
                }
                .btn-secondary {
                    background: #657786;
                }
                .btn-secondary:hover {
                    background: #4a5a6a;
                }
                .status {
                    padding: 15px;
                    border-radius: 8px;
                    margin: 15px 0;
                    font-weight: 500;
                }
                .status.idle {
                    background: #e8f5fe;
                    color: #1DA1F2;
                }
                .status.recording {
                    background: #fff3cd;
                    color: #856404;
                }
                .status.success {
                    background: #d4edda;
                    color: #155724;
                }
                .status.error {
                    background: #f8d7da;
                    color: #721c24;
                }
                .log {
                    background: #f7f9fa;
                    border: 1px solid #e1e8ed;
                    border-radius: 8px;
                    padding: 15px;
                    max-height: 300px;
                    overflow-y: auto;
                    font-family: 'Monaco', 'Courier New', monospace;
                    font-size: 13px;
                }
                .log-entry {
                    padding: 5px 0;
                    border-bottom: 1px solid #e1e8ed;
                }
                .log-entry:last-child {
                    border-bottom: none;
                }
                .timestamp {
                    color: #657786;
                    margin-right: 10px;
                }
                .example {
                    background: #f0f8ff;
                    padding: 10px;
                    border-radius: 6px;
                    margin: 5px 0;
                    font-size: 14px;
                    cursor: pointer;
                    border: 2px solid transparent;
                }
                .example:hover {
                    border-color: #1DA1F2;
                }
                .auth-status {
                    display: inline-block;
                    padding: 6px 12px;
                    border-radius: 20px;
                    font-size: 14px;
                    font-weight: 600;
                }
                .auth-status.connected {
                    background: #d4edda;
                    color: #155724;
                }
                .auth-status.disconnected {
                    background: #f8d7da;
                    color: #721c24;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🐦 Twitter Voice Poster - Test Interface</h1>
                    <p>Test your voice commands without using OMI device</p>
                    <div>
                        <span class="auth-status" id="authStatus">Checking...</span>
                    </div>
                </div>

                <div class="card">
                    <h2>Authentication</h2>
                    <div class="input-group">
                        <label for="uid">User ID (UID):</label>
                        <input type="text" id="uid" placeholder="Enter your OMI user ID" value="test_user_123">
                    </div>
                    <button class="btn" onclick="authenticate()">🔐 Authenticate Twitter</button>
                    <button class="btn btn-secondary" onclick="checkAuth()">🔍 Check Auth Status</button>
                </div>

                <div class="card">
                    <h2>Test Voice Commands</h2>
                    <div class="input-group">
                        <label for="voiceInput">What would you say to OMI:</label>
                        <textarea id="voiceInput" placeholder='Example: "Tweet Now, Just had an amazing idea about AI and creativity!"'></textarea>
                    </div>
                    <button class="btn" onclick="sendCommand()">🎤 Send Command</button>
                    <button class="btn btn-secondary" onclick="clearLogs()">🗑️ Clear Logs</button>
                    
                    <div id="status" class="status idle">
                        Status: Ready
                    </div>
                </div>

                <div class="card">
                    <h3>Quick Examples (Click to use)</h3>
                    <div class="example" onclick="useExample(this)">
                        Tweet Now, Just launched my new AI project and it's incredible!
                    </div>
                    <div class="example" onclick="useExample(this)">
                        Tweet Now, Beautiful sunset today. Nature never stops amazing me. End tweet.
                    </div>
                    <div class="example" onclick="useExample(this)">
                        Post Tweet, Excited to share my thoughts on the future of voice interfaces!
                    </div>
                    <div class="example" onclick="useExample(this)">
                        Tweet Now, Sometimes the best ideas come when you least expect them.
                    </div>
                </div>

                <div class="card">
                    <h2>Activity Log</h2>
                    <div id="log" class="log">
                        <div class="log-entry">
                            <span class="timestamp">Ready</span>
                            <span>Waiting for commands...</span>
                        </div>
                    </div>
                </div>
            </div>

            <script>
                const sessionId = 'test_session_' + Date.now();
                
                function addLog(message, type = 'info') {
                    const log = document.getElementById('log');
                    const entry = document.createElement('div');
                    entry.className = 'log-entry';
                    const time = new Date().toLocaleTimeString();
                    entry.innerHTML = `<span class="timestamp">[${time}]</span><span>${message}</span>`;
                    log.insertBefore(entry, log.firstChild);
                }
                
                function setStatus(message, type = 'idle') {
                    const status = document.getElementById('status');
                    status.textContent = message;
                    status.className = 'status ' + type;
                }
                
                async function checkAuth() {
                    const uid = document.getElementById('uid').value;
                    if (!uid) {
                        alert('Please enter a User ID');
                        return;
                    }
                    
                    try {
                        addLog('Checking authentication status...');
                        const response = await fetch(`/setup-completed?uid=${uid}`);
                        const data = await response.json();
                        
                        const authStatus = document.getElementById('authStatus');
                        if (data.is_setup_completed) {
                            authStatus.textContent = '✅ Connected';
                            authStatus.className = 'auth-status connected';
                            addLog('✅ Twitter account is connected!', 'success');
                        } else {
                            authStatus.textContent = '❌ Not Connected';
                            authStatus.className = 'auth-status disconnected';
                            addLog('❌ Twitter account not connected. Please authenticate.', 'error');
                        }
                    } catch (error) {
                        addLog('❌ Error checking auth: ' + error.message, 'error');
                    }
                }
                
                function authenticate() {
                    const uid = document.getElementById('uid').value;
                    if (!uid) {
                        alert('Please enter a User ID');
                        return;
                    }
                    
                    addLog('Opening Twitter authentication...');
                    window.open(`/auth?uid=${uid}`, '_blank');
                    
                    setTimeout(() => {
                        addLog('After authenticating, click "Check Auth Status" to verify.');
                    }, 1000);
                }
                
                async function sendCommand() {
                    const uid = document.getElementById('uid').value;
                    const voiceInput = document.getElementById('voiceInput').value;
                    
                    if (!uid || !voiceInput) {
                        alert('Please enter both User ID and voice command');
                        return;
                    }
                    
                    setStatus('🎤 Processing command...', 'recording');
                    addLog('📤 Sending: "' + voiceInput + '"');
                    
                    try {
                        // Simulate transcript segments
                        const segments = [{
                            text: voiceInput,
                            speaker: "SPEAKER_00",
                            speakerId: 0,
                            is_user: true,
                            start: 0.0,
                            end: 5.0
                        }];
                        
                        const response = await fetch(`/webhook?session_id=${sessionId}&uid=${uid}`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify(segments)
                        });
                        
                        const data = await response.json();
                        
                        if (response.ok) {
                            if (data.message.includes('✅')) {
                                setStatus(data.message, 'success');
                                addLog('✅ ' + data.message, 'success');
                            } else if (data.message.includes('❌')) {
                                setStatus(data.message, 'error');
                                addLog('❌ ' + data.message, 'error');
                            } else {
                                setStatus(data.message, 'recording');
                                addLog('📝 ' + data.message);
                            }
                        } else {
                            setStatus('❌ Error: ' + data.message, 'error');
                            addLog('❌ Error: ' + data.message, 'error');
                        }
                    } catch (error) {
                        setStatus('❌ Error sending command', 'error');
                        addLog('❌ Network error: ' + error.message, 'error');
                    }
                }
                
                function useExample(element) {
                    document.getElementById('voiceInput').value = element.textContent.trim();
                    addLog('📝 Example loaded: "' + element.textContent.trim() + '"');
                }
                
                function clearLogs() {
                    document.getElementById('log').innerHTML = '<div class="log-entry"><span class="timestamp">Cleared</span><span>Logs cleared</span></div>';
                    setStatus('Status: Ready', 'idle');
                }
                
                // Check auth on load
                window.onload = function() {
                    checkAuth();
                };
            </script>
        </body>
    </html>
    """)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "omi-twitter-integration"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", 8000))
    host = os.getenv("APP_HOST", "0.0.0.0")
    
    print("🐦 OMI Twitter Integration - Simple Mode")
    print("=" * 50)
    print("✅ Using in-memory storage (no database)")
    print(f"🚀 Starting on {host}:{port}")
    print("⚠️  Note: Data resets when server restarts")
    print("=" * 50)
    
    uvicorn.run(
        "main_simple:app",
        host=host,
        port=port,
        reload=True
    )

