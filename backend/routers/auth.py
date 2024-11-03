from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
import os
import json

router = APIRouter()

def get_firebase_config():
    """Get Firebase config from environment variables"""
    required_configs = [
        'FIREBASE_API_KEY',
        'FIREBASE_AUTH_DOMAIN',
        'FIREBASE_PROJECT_ID',
        'FIREBASE_STORAGE_BUCKET',
        'FIREBASE_MESSAGING_SENDER_ID',
        'FIREBASE_APP_ID'
    ]
    
    # Check if all required configs are present
    missing = [key for key in required_configs if not os.getenv(key)]
    if missing:
        return None
        
    return {
        'apiKey': os.getenv('FIREBASE_API_KEY'),
        'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN'),
        'projectId': os.getenv('FIREBASE_PROJECT_ID'),
        'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET'),
        'messagingSenderId': os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
        'appId': os.getenv('FIREBASE_APP_ID')
    }

@router.get("/login", response_class=HTMLResponse)
async def auth_page():
    """Serve Firebase Authentication page if config is available"""
    firebase_config = get_firebase_config()
    
    if not firebase_config:
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Firebase Authentication</title></head>
        <body>
            <h2>Firebase Authentication Not Available</h2>
            <p>Firebase configuration is not complete. Please set all required environment variables.</p>
            <p>Goto Firebase Console > Project Settings > General > Web API Key (Config) to get the required variables.</p>
            <p>As per <a href="https://firebase.google.com/docs/auth/web/apple?hl=en&authuser=0">Firebase Documentation</a>:</p>
            <p>Apple support requires additional configuration.</p>
            <p>Required variables:</p>
            <ul>
                <li>FIREBASE_API_KEY</li>
                <li>FIREBASE_AUTH_DOMAIN</li>
                <li>FIREBASE_PROJECT_ID</li>
                <li>FIREBASE_STORAGE_BUCKET</li>
                <li>FIREBASE_MESSAGING_SENDER_ID</li>
                <li>FIREBASE_APP_ID</li>
            </ul>
        </body>
        </html>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Firebase Authentication</title>
        <script src="https://www.gstatic.com/firebasejs/10.8.0/firebase-app-compat.js"></script>
        <script src="https://www.gstatic.com/firebasejs/10.8.0/firebase-auth-compat.js"></script>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 40px auto;
                padding: 20px;
                text-align: center;
            }}
            .button-container {{
                display: flex;
                flex-direction: column;
                gap: 10px;
                align-items: center;
                margin: 20px 0;
            }}
            button {{
                padding: 12px 24px;
                font-size: 16px;
                cursor: pointer;
                border: none;
                border-radius: 5px;
                display: flex;
                align-items: center;
                gap: 10px;
                min-width: 250px;
            }}
            .google-btn {{
                background-color: #fff;
                color: #757575;
                border: 1px solid #ddd;
            }}
            .apple-btn {{
                background-color: #000;
                color: #fff;
            }}
            pre {{
                background: #f5f5f5;
                padding: 15px;
                border-radius: 5px;
                white-space: pre-wrap;
                word-wrap: break-word;
                text-align: left;
                margin-top: 20px;
            }}
            .token-container {{
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <h2>Firebase Authentication for API Testing</h2>
        <p>Sign in to get a valid Firebase token for API testing.</p>
        
        <div class="button-container">
            <button onclick="signInWithGoogle()" class="google-btn">
                <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" width="18" height="18">
                Sign in with Google
            </button>
            <button onclick="signInWithApple()" class="apple-btn">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M17.05 20.28c-.98.95-2.05.88-3.08.38-1.08-.52-2.07-.53-3.2 0-1.44.71-2.2.51-3.08-.38C3.33 16.08 3.63 9.84 8.14 9.43c1.32.07 2.23.48 3.03.49.82.01 1.67-.35 3.03-.49 4.24-.35 4.98 5.13.85 10.85zm-4.24-14.5c.09-2.85 2.35-4.32 2.46-4.4-1.33-1.97-3.41-2.24-4.14-2.28-1.77-.18-3.45 1.04-4.35 1.04-.89 0-2.27-1.02-3.74-.99-1.92.03-3.69 1.12-4.68 2.84-2 3.47-.51 8.62 1.44 11.44.95 1.38 2.09 2.93 3.58 2.87 1.44-.06 1.98-.93 3.72-.93s2.23.93 3.75.9c1.55-.03 2.53-1.41 3.48-2.79.78-1.14 1.36-2.43 1.58-2.95-.04-.02-3.03-1.16-3.06-4.61-.03-2.89 2.35-4.27 2.46-4.34-.02-.01-1.7-.66-4.5-.66z"/>
                </svg>
                Sign in with Apple
            </button>
        </div>
        
        <div class="token-container">
            <pre id="token"></pre>
        </div>
        
        <script>
            // Initialize Firebase
            const firebaseConfig = {firebase_config};
            firebase.initializeApp(firebaseConfig);
            
            async function signInWithGoogle() {{
                try {{
                    const provider = new firebase.auth.GoogleAuthProvider();
                    await signIn(provider);
                }} catch (error) {{
                    handleError(error);
                }}
            }}
            
            async function signInWithApple() {{
                try {{
                    const provider = new firebase.auth.OAuthProvider('apple.com');
                    await signIn(provider);
                }} catch (error) {{
                    handleError(error);
                }}
            }}
            
            async function signIn(provider) {{
                try {{
                    const result = await firebase.auth().signInWithPopup(provider);
                    const token = await result.user.getIdToken();
                    
                    const tokenDisplay = document.getElementById('token');
                    tokenDisplay.textContent = `Your Bearer token (click to copy):\n\nBearer ${{token}}`;
                    
                    // Add click-to-copy functionality
                    tokenDisplay.style.cursor = 'pointer';
                    tokenDisplay.onclick = async () => {{
                        try {{
                            await navigator.clipboard.writeText(`Bearer ${{token}}`);
                            alert('Token copied to clipboard!');
                        }} catch (err) {{
                            console.error('Failed to copy:', err);
                        }}
                    }};
                }} catch (error) {{
                    handleError(error);
                }}
            }}
            
            function handleError(error) {{
                console.error(error);
                if (error.code === 'auth/operation-not-allowed') {{
                    alert('This sign-in method is not enabled. Please enable it in the Firebase console under Authentication > Sign-in methods.');
                }} else {{
                    alert('Error signing in: ' + error.message);
                }}
            }}
        </script>
    </body>
    </html>
    """.replace('{firebase_config}', json.dumps(firebase_config))