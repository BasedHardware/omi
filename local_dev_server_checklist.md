# Local Dev Server Checklist for Omi

Use this checklist to ensure you have everything set up for backend and app development.

## I. Ngrok Setup

1. **Install and Configure Ngrok**:
   * Sign up for a free account on [https://ngrok.com/](https://ngrok.com/)
   * Download and install Ngrok
   * Follow their instructions to authenticate: `ngrok config add-authtoken <your-token>`

2. **Set Up a Static Domain**:
   * During onboarding, Ngrok will provide you with a static domain
   * In your ngrok dashboard, navigate to Domains and ensure you have a static domain (e.g., `your-subdomain.ngrok-free.app`)

## II. Backend Configuration (`backend/`)

1. **Create Central Configuration File**:
   * Create a file in the project root directory called `dev-config.sh`:
   ```bash
   # Create a file in your project root
   touch dev-config.sh
   chmod +x dev-config.sh
   ```
   * Edit `dev-config.sh` with the following content (replace with your ngrok domain):
   ```bash
   #!/bin/bash
   # Central configuration for development environment

   # Set your ngrok base URL here (only edit this one place)
   export NGROK_BASE_URL="https://your-subdomain.ngrok-free.app/"

   # Update app environment file
   echo "API_BASE_URL=$NGROK_BASE_URL" > app/.dev.env

   # Update backend environment file (preserve other variables)
   if [ -f backend/.dev.env ]; then
     # Update existing backend env file, replacing API_BASE_URL line
     sed -i.bak "s|^API_BASE_URL=.*|API_BASE_URL=$NGROK_BASE_URL|g" backend/.dev.env
     echo "✅ Updated backend/.dev.env with API_BASE_URL=$NGROK_BASE_URL"
   elif [ -f backend/.env ]; then
     # Update existing backend env file, replacing API_BASE_URL line
     sed -i.bak "s|^API_BASE_URL=.*|API_BASE_URL=$NGROK_BASE_URL|g" backend/.env
     echo "✅ Updated backend/.env with API_BASE_URL=$NGROK_BASE_URL"
   else
     echo "⚠️ No backend environment file found. Create one first."
   fi

   # Also update BASE_API_URL if present (for services that call back to your backend)
   if grep -q "^BASE_API_URL=" backend/.dev.env; then
     sed -i.bak "s|^BASE_API_URL=.*|BASE_API_URL=$NGROK_BASE_URL|g" backend/.dev.env
     echo "✅ Updated backend/.dev.env with BASE_API_URL=$NGROK_BASE_URL"
   elif grep -q "^BASE_API_URL=" backend/.env; then
     sed -i.bak "s|^BASE_API_URL=.*|BASE_API_URL=$NGROK_BASE_URL|g" backend/.env
     echo "✅ Updated backend/.env with BASE_API_URL=$NGROK_BASE_URL"
   fi

   # Print next steps
   echo ""
   echo "🚀 Configuration updated!"
   echo "Next steps:"
   echo "1. Start ngrok: ngrok http --domain=$NGROK_BASE_URL 8000"
   echo "2. Start backend: cd backend && source venv/bin/activate && uvicorn main:app --reload --env-file .dev.env"
   echo "3. Run your app"
   ```

2. **Run the Configuration Script**:
   * Whenever you need to change your ngrok URL, just:
     1. Edit the `NGROK_BASE_URL` in `dev-config.sh`
     2. Run `./dev-config.sh`
     3. This will update all necessary files with the new URL

3. **Backend Environment File (`.env` or `.dev.env`)**:
   * The backend loads environment variables from a file. The default Uvicorn command in docs uses `--env-file .env`. You indicated you have a `backend/.dev.env`.
   * **Action**: Decide if you will:
     * Use `backend/.env`: If so, copy/rename your `backend/.dev.env` to `backend/.env`.
     * Use `backend/.dev.env`: If so, you must modify the Uvicorn startup command (see step 5).
   * **Action**: Edit your chosen backend environment file (e.g., `backend/.env` or `backend/.dev.env`). Based on your provided `backend/.dev.env` and the goal of local hosting:
     * **Ensure `API_BASE_URL` is present**: This will be set by the `dev-config.sh` script.
     * **Review/Update `HOSTED_PUSHER_API_URL`**:
       * Your current value: `HOSTED_PUSHER_API_URL=http://192.168.1.12:8098`
       * **Question for you**: Does this Pusher service need to be publicly accessible (e.g., for the app to connect directly, or for external webhooks)?
       * If **yes**: You'll need to run it locally (if it's your own service, e.g., from `backend/pusher/`), expose its local port (e.g., 8001, must be different from main backend) via a separate ngrok tunnel (e.g., `ngrok http --domain=pusher-your-subdomain.ngrok-free.app 8001`), and set `HOSTED_PUSHER_API_URL` to this new ngrok URL.
       * If **no** (it's only accessed by the backend locally, and the backend can reach `192.168.1.12:8098`), it *might* be okay, but for a fully self-contained ngrok-based dev setup, tunneling is recommended if it's part of the system under test.

4. **Google Cloud Authentication**:
   * Ensure you have valid Google credentials in `backend/google-credentials-dev.json` (or with file path that matches your GOOGLE_APPLICATION_CREDENTIALS in `.env`).

5. **Start the Backend Server**:
   * In the `backend/` directory (ensure your Python virtual environment is activated if you use one):
   * If using `backend/.env`:
     ```bash
     uvicorn main:app --reload --env-file .env --port 8000 --host 0.0.0.0
     ```
   * If using `backend/.dev.env`:
     ```bash
     uvicorn main:app --reload --env-file .dev.env --port 8000 --host 0.0.0.0
     ```
     (Adjust port if necessary).
   * If running other services locally (like Pusher, VAD, etc.) on different ports, start them and their respective ngrok tunnels if needed.

## III. App (Flutter) Configuration (`app/`)

1. **App Environment File (`app/.dev.env`)**:
   * The Flutter app's `DevEnv` (in `app/lib/env/dev_env.dart`) is configured to load from `path: '.dev.env'`.
   * **This file will be automatically updated by the `dev-config.sh` script.**

2. **Review Other External Service URLs in App Code**:
   * `app/lib/backend/http/openai.dart` uses `Env.openAIAPIKey` and makes direct calls to `https://api.openai.com/v1/`.
     * **Question for you**: Is direct access to OpenAI intended, or should requests be proxied through your `your-subdomain.ngrok-free.app`? If proxying, `app/lib/backend/http/openai.dart` would need to change its base URL, and your backend would need to handle these proxy requests. This checklist currently assumes direct access.

## IV. Development Workflow

1. **Whenever your ngrok URL changes**:
   * Edit the `NGROK_BASE_URL` in `dev-config.sh`
   * Run `./dev-config.sh` to update all necessary files
   * Start ngrok and the backend using the commands provided by the script

2. **Recommended Terminal Setup**:
   * Terminal 1: Run ngrok
     ```bash
     ngrok http --domain=your-subdomain.ngrok-free.app 8000
     ```
   * Terminal 2: Run the backend
     ```bash
     cd backend
     source venv/bin/activate && uvicorn main:app --reload --env-file .dev.env
     ```
   * Terminal 3: Flutter development
     ```bash
     cd app
     flutter run
     ```

## V. Troubleshooting

* If you encounter SSL certificate errors during model downloads, add this to `utils/stt/vad.py`:
  ```python
  import ssl
  ssl._create_default_https_context = ssl._create_unverified_context
  ```
* Make sure your ngrok session is active and your app is using the correct API_BASE_URL
* Verify that the backend server is running and accessible via the ngrok URL
* Check for any CORS issues if you encounter network errors in the app
* For opus-related errors, ensure you've installed the system-level opus library as specified in the backend README