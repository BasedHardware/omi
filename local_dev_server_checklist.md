# Local Dev Server Setup Checklist (Self-Hosted via Ngrok)

This checklist outlines the steps and file modifications required to run the application with a locally hosted backend server, accessible via `https://opossum-cuddly-ultimately.ngrok-free.app`.

## I. Prerequisites

1.  **Ngrok Account & Setup**:
    *   Ensure you have an ngrok account.
    *   Install the ngrok CLI.
    *   Authenticate ngrok: `ngrok config add-authtoken <YOUR_NGROK_AUTH_TOKEN>`
    *   Ensure your static domain `opossum-cuddly-ultimately.ngrok-free.app` is correctly configured in your ngrok dashboard to point to your desired local port.

## II. Backend Configuration (`backend/`)

1.  **Determine Backend Port**:
    *   The backend server (FastAPI + Uvicorn) typically runs on port **8000** for local development (as per `docs` and `uvicorn` commands: `uvicorn main:app --port 8000`).
    *   If running the backend via Docker (using `backend/Dockerfile`), it exposes port **8080**.
    *   **Action**: Confirm which port your backend will listen on locally. For this guide, we'll primarily assume port **8000**.

2.  **Start Ngrok Tunnel**:
    *   Open a terminal and run (replace `8000` with your actual local backend port if different, e.g., `8080` for Docker):
        ```bash
        ngrok http --domain=opossum-cuddly-ultimately.ngrok-free.app 8000
        ```
    *   Keep this tunnel running. Your public URL will be `https://opossum-cuddly-ultimately.ngrok-free.app`.

3.  **Configure Backend Environment Variables**:
    *   Navigate to the `backend/` directory.
    *   If it doesn't exist, create a `.env` file by copying `backend/.env.template`:
        ```bash
        cp .env.template .env
        ```
    *   Edit `backend/.env`. The following variables might need to be set or updated to use your ngrok URL. **Review each one based on your setup.**

        *   `BASE_API_URL`: This should be your primary ngrok URL for callbacks or services that need to reach the backend externally (e.g., Stripe webhooks).
            ```
            BASE_API_URL=https://opossum-cuddly-ultimately.ngrok-free.app/
            ```

        *   `HOSTED_PUSHER_API_URL`:
            *   **Question for you**: Is the `pusher` service (from `backend/pusher/`) also being run locally and needs to be accessible via ngrok?
            *   If **yes**, and it runs as a separate service on a different port, it will need its own ngrok tunnel or a more complex ngrok setup (e.g., different ngrok domain or path routing if your ngrok plan supports it). If it runs on, for example, port 8001 locally and you tunnel it with `ngrok http --domain=pusher-your-domain.ngrok-free.app 8001`, then set that URL here.
            *   If it runs and is accessible via the *same* ngrok tunnel as the main backend (e.g., `https://opossum-cuddly-ultimately.ngrok-free.app/pusher/`), then update accordingly.
            *   If you are **not** running the pusher service locally or it doesn't need to be externally accessible via this ngrok domain, configure as per its requirements.
            *   The documentation (`docs/docs-old/developer/backend/Backend_Setup.mdx`) suggests starting pusher via `uvicorn pusher.main:app --reload --env-file .env --port 8000`. If this is the case *and* it's a separate process from the main backend, it cannot use the same port 8000 as the main backend simultaneously on the same machine. It would need a different port (e.g., 8001).

        *   `DEEPGRAM_SELF_HOSTED_URL` (used by `backend/utils/stt/streaming.py`):
            *   **Question for you**: Are you self-hosting Deepgram, and does it need to be accessible via an ngrok URL for the backend to use?
            *   If yes, set this to its ngrok URL (e.g., `https://your-deepgram-ngrok.app`).
            *   If no (using Deepgram cloud or a non-ngrok accessible local instance), configure as appropriate.

        *   `HUME_CALLBACK_URL` (used by `backend/utils/other/hume.py`):
            *   If Hume AI needs to send callbacks to your *local* development server, this must be your ngrok URL + the specific callback path.
                ```
                HUME_CALLBACK_URL=https://opossum-cuddly-ultimately.ngrok-free.app/your-hume-callback-endpoint
                ```
            *   Otherwise, configure as needed for your Hume setup.

4.  **Review Other External Service URLs in Backend Code**:
    *   `backend/utils/llm.py` uses `OPENROUTER_API_KEY` and `base_url="https://openrouter.ai/api/v1"`.
        *   **Question for you**: Is direct access to OpenRouter intended, or should requests to it be proxied through your ngrok setup? If proxying is needed, this code and potentially your ngrok setup would need modification. For now, this checklist assumes direct access.

5.  **Start the Backend Server**:
    *   In the `backend/` directory (ensure your Python virtual environment is activated if you use one):
        ```bash
        uvicorn main:app --reload --env-file .env --port 8000 --host 0.0.0.0
        ```
        (Adjust port if necessary, e.g., to 8080 if using Docker and forwarding that).
    *   If running the Pusher service (`backend/pusher/`) locally as a *separate* process, start it as well. Ensure it runs on a *different port* than the main backend (e.g., 8001) and set up a separate ngrok tunnel for it if it needs to be externally accessible, then update `HOSTED_PUSHER_API_URL` accordingly.
        ```bash
        # Example for pusher on port 8001, in backend/pusher/ (adjust .env path if needed)
        # uvicorn main:app --reload --env-file ../.env --port 8001 --host 0.0.0.0
        ```

## III. App (Flutter) Configuration (`app/`)

1.  **Configure App Environment Variables**:
    *   The Flutter app uses the `envied` package. Environment configuration for development is loaded from `.dev.env`.
    *   **Action**: Locate or create the file named `.dev.env` at the **root of your project repository** (alongside `app/`, `backend/` etc.). The `envied` configuration `@Envied(path: '.dev.env')` in `app/lib/env/dev_env.dart` implies it looks for this file relative to where the build command is run, typically the project root.
    *   Edit this `PROJECT_ROOT/.dev.env` file and ensure `API_BASE_URL` is set:
        ```
        API_BASE_URL=https://opossum-cuddly-ultimately.ngrok-free.app/
        ```
        *(A trailing slash seems to be expected based on usage in `app/lib/backend/http/api/` files and the validator in `app/lib/pages/onboarding/custom_auth/backend_url.dart`)*

2.  **Review Other External Service URLs in App Code**:
    *   `app/lib/backend/http/openai.dart` uses `Env.openAIAPIKey` and makes direct calls to `https://api.openai.com/v1/`.
        *   **Question for you**: Is direct access to OpenAI intended, or should requests to it be proxied through your `opossum-cuddly-ultimately.ngrok-free.app`? If proxying, this code would need to be changed to use a base URL that points to your ngrok, and your backend would need to handle proxying these requests. For now, this checklist assumes direct access.

3.  **Rebuild/Restart the App**:
    *   After changing/creating the `.dev.env` file, `envied` needs to regenerate its files.
    *   Run the following in your `app/` directory (or project root if your Flutter commands are run from there):
        ```bash
        flutter clean
        flutter pub get
        flutter pub run build_runner build --delete-conflicting-outputs
        # Then run your app
        flutter run
        ```

## IV. Summary of Files to Check/Modify/Create

*   **Project Root**:
    *   `.dev.env` (Create if it doesn't exist)
        *   Set `API_BASE_URL=https://opossum-cuddly-ultimately.ngrok-free.app/`

*   **Backend (`backend/`)**:
    *   `.env` (Create by copying `backend/.env.template` if it doesn't exist)
        *   Set/Verify `BASE_API_URL`
        *   Set/Verify `HOSTED_PUSHER_API_URL` (consider if pusher runs locally, its port, and ngrok)
        *   Set/Verify `DEEPGRAM_SELF_HOSTED_URL` (if self-hosting Deepgram via ngrok)
        *   Set/Verify `HUME_CALLBACK_URL` (if callbacks target local ngrok)
    *   Potentially `backend/utils/llm.py` (If OpenRouter URL needs to be proxied).
    *   Potentially `backend/pusher/.env` (if pusher uses its own .env and runs as a separate service).

*   **App (Flutter) (`app/`)**:
    *   Potentially `app/lib/backend/http/openai.dart` (If OpenAI URL needs to be proxied).

## V. Key Considerations & Outstanding Questions for You

*   **Backend Port**: Confirm if backend runs on port `8000` (direct `uvicorn`) or `8080` (Docker). Ngrok must point to this.
*   **Pusher Service (`HOSTED_PUSHER_API_URL`)**:
    *   Will the `pusher` service (`backend/pusher/`) run locally?
    *   If yes:
        *   What port will it use (must be different from the main backend if on the same machine)?
        *   Will it need its own ngrok tunnel, or be routed via `opossum-cuddly-ultimately.ngrok-free.app` (e.g., path-based)? How will `HOSTED_PUSHER_API_URL` be set?
*   **Deepgram (`DEEPGRAM_SELF_HOSTED_URL`)**: Self-hosting Deepgram and routing via ngrok?
*   **Hume AI Callback (`HUME_CALLBACK_URL`)**: Does this need to point to your ngrok URL?
*   **OpenAI URL (in Flutter App)**: Proxy via ngrok or direct access?
*   **OpenRouter URL (in Backend)**: Proxy via ngrok or direct access?
*   **Location of `.dev.env` for Flutter app**: This guide assumes `PROJECT_ROOT/.dev.env`. Please verify. If `envied` is configured differently or run from `app/` dir, it might be `app/.dev.env`. The key is that `dev_env.dart`'s `@Envied(path: '.dev.env')` can find it.

This checklist should guide you through the process. Please review the questions, as your specific setup details will determine the exact values for some of these configurations.