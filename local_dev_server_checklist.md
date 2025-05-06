# Local Dev Server Setup Checklist (Self-Hosted via Ngrok)

This checklist outlines the steps and file modifications required to run the application with a locally hosted backend server, accessible via `https://opossum-cuddly-ultimately.ngrok-free.app`.

## I. Prerequisites

1.  **Ngrok Account & Setup**:
    *   Ensure you have an ngrok account.
    *   Install the ngrok CLI.
    *   Authenticate ngrok: `ngrok config add-authtoken <YOUR_NGROK_AUTH_TOKEN>`
    *   Ensure your static domain `opossum-cuddly-ultimately.ngrok-free.app` is correctly configured in your ngrok dashboard.

## II. Backend Configuration (`backend/`)

1.  **Determine Backend Port**:
    *   The backend server (FastAPI + Uvicorn) typically runs on port **8000** for local development (as per `docs` and `uvicorn` commands: `uvicorn main:app --port 8000`).
    *   If running the backend via Docker (using `backend/Dockerfile`), it exposes port **8080**.
    *   **Action**: Confirm which port your backend will listen on locally. This guide primarily assumes port **8000**.

2.  **Google Cloud Credentials**:
    *   Your backend environment configuration likely specifies a `GOOGLE_APPLICATION_CREDENTIALS` file (e.g., `GOOGLE_APPLICATION_CREDENTIALS=google-credentials-dev.json` was found in a `.dev.env`).
    *   **Action**: Ensure the specified JSON credentials file (e.g., `google-credentials-dev.json`) is present in your `backend/` directory. If your file is named differently (e.g., `google-credentials-modal-dev.json`), rename it to match the value in your backend environment file.

3.  **Backend Environment File (`.env` or `.dev.env`)**:
    *   The backend loads environment variables from a file. The default Uvicorn command in docs uses `--env-file .env`. You indicated you have a `backend/.dev.env`.
    *   **Action**: Decide if you will:
        *   Use `backend/.env`: If so, copy/rename your `backend/.dev.env` to `backend/.env`.
        *   Use `backend/.dev.env`: If so, you must modify the Uvicorn startup command (see step 5).
    *   **Action**: Edit your chosen backend environment file (e.g., `backend/.env` or `backend/.dev.env`). Based on your provided `backend/.dev.env` and the goal of local hosting:
        *   **Ensure `BASE_API_URL` is present and correct**: This is for services that call back to your backend (like Stripe).
            ```env
            BASE_API_URL=https://opossum-cuddly-ultimately.ngrok-free.app/
            ```
        *   **Review/Update `HOSTED_PUSHER_API_URL`**:
            *   Your current value: `HOSTED_PUSHER_API_URL=http://192.168.1.12:8098`
            *   **Question for you**: Does this Pusher service need to be publicly accessible (e.g., for the app to connect directly, or for external webhooks)?
            *   If **yes**: You'll need to run it locally (if it's your own service, e.g., from `backend/pusher/`), expose its local port (e.g., 8001, must be different from main backend) via a separate ngrok tunnel (e.g., `ngrok http --domain=pusher-your-subdomain.ngrok-free.app 8001`), and set `HOSTED_PUSHER_API_URL` to this new ngrok URL.
            *   If **no** (it's only accessed by the backend locally, and the backend can reach `192.168.1.12:8098`), it *might* be okay, but for a fully self-contained ngrok-based dev setup, tunneling is recommended if it's part of the system under test.
        *   **Review/Update `HUME_CALLBACK_URL`**:
            *   Your current value: `HUME_CALLBACK_URL=https://based-hardware--backend-api.modal.run/v1/agents/hume/callback`
            *   **Action for you**: If Hume AI callbacks should target your local server, change this to:
                ```env
                HUME_CALLBACK_URL=https://opossum-cuddly-ultimately.ngrok-free.app/v1/agents/hume/callback
                ```
                (Verify `/v1/agents/hume/callback` is the correct path).
        *   **Review Other Service URLs (Modal, etc.)**: Your `backend/.dev.env` has:
            *   `HOSTED_VAD_API_URL=https://based-hardware-development--vad-endpoint.modal.run`
            *   `HOSTED_SPEECH_PROFILE_API_URL=https://based-hardware-development--speech-profile-endpoint.modal.run`
            *   **Question for you**: Are these services you intend to run locally as part of your self-hosted setup? If yes, you'll need to set them up, determine their local ports, expose them via ngrok, and update these URLs. If no (you'll continue using these hosted Modal instances), leave them as is.
        *   Ensure all other necessary variables (API keys like `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, database connections like Redis/Pinecone/Typesense, `ADMIN_KEY`, etc.) are correctly configured as per your `backend/.dev.env` and project needs.

4.  **Start Ngrok Tunnel for Main Backend**:
    *   Open a terminal and run (replace `8000` with your actual local backend port, e.g., `8080` if using Docker and it exposes that):
        ```bash
        ngrok http --domain=opossum-cuddly-ultimately.ngrok-free.app 8000
        ```
    *   Keep this tunnel running.

5.  **Start the Backend Server**:
    *   In the `backend/` directory (ensure your Python virtual environment is activated if you use one):
    *   If using `backend/.env`:
        ```bash
        uvicorn main:app --reload --env-file .env --port 8000 --host 0.0.0.0
        ```
    *   If using `backend/.dev.env`:
        ```bash
        uvicorn main:app --reload --env-file .dev.env --port 8000 --host 0.0.0.0
        ```
        (Adjust port if necessary).
    *   If running other services locally (like Pusher, VAD, etc.) on different ports, start them and their respective ngrok tunnels if needed.

## III. App (Flutter) Configuration (`app/`)

1.  **App Environment File (`PROJECT_ROOT/.dev.env`)**:
    *   The Flutter app's `DevEnv` (in `app/lib/env/dev_env.dart`) is configured to load from `path: '.dev.env'`, which is relative to the build execution directory (typically project root).
    *   **Action**: Ensure the file `PROJECT_ROOT/.dev.env` (i.e., in the same directory as `app/` and `backend/` folders) exists and contains:
        ```
        API_BASE_URL=https://opossum-cuddly-ultimately.ngrok-free.app/
        ```
        *(A trailing slash is generally good practice and seems expected by your app's code).*
    *   The empty `app/.env.template` is likely not used for the dev environment due to the explicit path in `DevEnv`.

2.  **Review Other External Service URLs in App Code**:
    *   `app/lib/backend/http/openai.dart` uses `Env.openAIAPIKey` and makes direct calls to `https://api.openai.com/v1/`.
        *   **Question for you**: Is direct access to OpenAI intended, or should requests be proxied through your `opossum-cuddly-ultimately.ngrok-free.app`? If proxying, `app/lib/backend/http/openai.dart` would need to change its base URL, and your backend would need to handle these proxy requests. This checklist currently assumes direct access.

3.  **Rebuild/Restart the App**:
    *   After confirming/creating `PROJECT_ROOT/.dev.env`, `envied` needs to regenerate its files.
    *   Run from your project root (or `app/` directory, depending on your Flutter project structure):
        ```bash
        flutter clean
        flutter pub get
        flutter pub run build_runner build --delete-conflicting-outputs
        # Then run your app
        flutter run
        ```

## IV. Summary of Files to Check/Modify/Create

*   **Project Root (`/Users/pk/repo/_OMI/omi_monorepo.worktrees/self-dev-backend/`)**:
    *   `.dev.env` (Ensure it exists)
        *   Set/Verify `API_BASE_URL=https://opossum-cuddly-ultimately.ngrok-free.app/`

*   **Backend (`backend/`)**:
    *   Your chosen environment file: `backend/.env` or `backend/.dev.env`.
        *   Add/Set/Verify `BASE_API_URL`.
        *   Review/Update `HOSTED_PUSHER_API_URL` (local IP vs. ngrok).
        *   Review/Update `HUME_CALLBACK_URL` (Modal URL vs. ngrok).
        *   Review `HOSTED_VAD_API_URL`, `HOSTED_SPEECH_PROFILE_API_URL` (Modal vs. local/ngrok).
        *   Ensure all other required API keys and service credentials are correct.
    *   `google-credentials-dev.json` (or the name specified in `GOOGLE_APPLICATION_CREDENTIALS`): Ensure this file exists in `backend/`.
    *   Potentially `backend/utils/llm.py` (if OpenRouter URL needs to be proxied - currently assumed direct).

*   **App (Flutter) (`app/`)**:
    *   Potentially `app/lib/backend/http/openai.dart` (if OpenAI URL needs to be proxied - currently assumed direct).

## V. Key Considerations & Outstanding Questions for You (Recap)

*   **Backend Env File Name**: Will you use `backend/.env` (by renaming/copying) or `backend/.dev.env` (and adjust uvicorn command)?
*   **Pusher Service (`HOSTED_PUSHER_API_URL`)**: Local IP okay, or does it need ngrok for public access?
*   **Hume AI Callback (`HUME_CALLBACK_URL`)**: Change to your ngrok URL?
*   **Other Backend Services (VAD, Speech Profile)**: Continue using Modal, or set up locally with ngrok?
*   **OpenAI URL (in Flutter App)**: Proxy via ngrok or direct access?
*   **OpenRouter URL (in Backend)**: Proxy via ngrok or direct access? (Currently assumed direct for both OpenAI/OpenRouter).

This checklist should guide you through the process. Please address the "Action" items and "Question for you" points.