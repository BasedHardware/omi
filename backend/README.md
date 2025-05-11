# Omi Backend Setup

This README provides a quick setup guide for the Omi backend. For a comprehensive step-by-step guide with detailed explanations, please refer to the [Backend Setup Documentation](https://docs.omi.me/docs/developer/backend/Backend_Setup).

## Quick Setup Steps

1. Install the google-cloud-sdk
   - Mac: `brew install google-cloud-sdk`
   - Windows: `choco install gcloudsdk`
   - Nix envdir: It should be pre-installed

2. You will need to have your own Google Cloud Project with Firebase enabled. If you've already set up Firebase for the Omi app, you're good to go. If not, please refer to the [Firebase Setup Guide](https://firebase.google.com/docs/projects/learn-more).
   - **IMPORTANT:** Make sure you have the [`Cloud Resource Manager API`](https://console.cloud.google.com/apis/library/cloudresourcemanager.googleapis.com), [`Firebase Management API`](https://console.cloud.google.com/apis/library/firebase.googleapis.com), and [`Cloud Firestore API`](https://console.developers.google.com/apis/api/firestore.googleapis.com/overview) enabled in the [Google Cloud API Console](https://console.cloud.google.com/apis/dashboard) **before proceeding to the next steps**. Failure to enable these APIs will result in authentication errors.

3. Run the following commands one by one to authenticate with Google Cloud:
   ```bash
   gcloud auth login
   gcloud config set project <project-id>
   gcloud auth application-default login --project <project-id>
   ```
   Replace `<project-id>` with your Google Cloud Project ID.
   This should generate the `application_default_credentials.json` file in the `~/.config/gcloud` directory. This file is read automatically by gcloud in Python.

4. Install Python
   - Mac: `brew install python`
   - Windows: `choco install python`
   - Nix envdir: It should be pre-installed

5. Install `pip` if it doesn't exist (follow instructions on [pip installation page](https://pip.pypa.io/en/stable/installation/))

6. Install `git` and `ffmpeg`
   - Mac: `brew install git ffmpeg`
   - Windows: `choco install git.install ffmpeg`
   - Nix envdir: These should be pre-installed

7. Install `opus` (required for audio processing)
   - Mac: `brew install opus`
   - Windows: You should already have it if you're on Windows 10 version 1903 and above

8. Move to the backend directory: `cd backend`

9. Create your environment file: `cp .env.template .env`

10. Set up Redis
    - [Upstash](https://console.upstash.com/) is recommended - sign up and create a free instance

11. Add the necessary API keys in the `.env` file:
    - [OpenAI API Key](https://platform.openai.com/settings/organization/api-keys)
    - [Deepgram API Key](https://console.deepgram.com/api-keys)
    - Redis credentials from your [Upstash Console](https://console.upstash.com/)
    - Set `ADMIN_KEY` to a temporary value (e.g., `123`) for local development
    - **IMPORTANT:** For Pinecone vector database:
      - Make sure to set `PINECONE_INDEX_NAME` to the name of your Pinecone index
      - If you don't have a Pinecone index yet, [create one in the Pinecone Console](https://app.pinecone.io/)
      - The index should be created with the appropriate dimension setting (e.g., 1536 for OpenAI embeddings)

12. Install Python dependencies (choose one of the following approaches):

    **Option A: Using a virtual environment (recommended)**
    ```bash
    # Create a virtual environment
    python -m venv venv

    # Activate the virtual environment
    # On Windows:
    venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate

    # Install dependencies within the virtual environment
    pip install -r requirements.txt
    ```
    You should see `(venv)` at the beginning of your command prompt when the virtual environment is active.

    **Option B: Direct installation**
    ```bash
    # Install dependencies globally
    pip install -r requirements.txt
    ```

13. Sign up on [ngrok](https://ngrok.com/) and follow the steps to configure it
    - During onboarding, get your authentication token and run `ngrok config add-authtoken <your-token>`

14. During the onboarding flow, under the `Static Domain` section, Ngrok should provide you with a static domain and a command to point your localhost to that static domain. Replace the port from 80 to 8000 in that command and run it in your terminal:
    ```bash
    ngrok http --domain=example.ngrok-free.app 8000
    ```

15. Start the backend server:
    ```bash
    uvicorn main:app --reload --env-file .env
    ```

16. Troubleshooting: If you get any error mentioning "no internet connection" while downloading models, add the following lines in the `utils/stt/vad.py` file after the import statements:
    ```python
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
    ```

17. Now try running the server again: `uvicorn main:app --reload --env-file .env`

18. In your Omi app's environment, set `API_BASE_URL` to the URL provided by ngrok (e.g., `https://example.ngrok-free.app`)

19. Your app should now be using your local backend

20. If you used a virtual environment, when you're done, deactivate it by running:
    ```bash
    deactivate
    ```

## Running with Logging Enabled

1. Start the backend with logging enabled:
   Running the server with your virtual environment:

   ```bash
   # Enable logging
   source venv/bin/activate && uvicorn main:app --reload --env-file .env
   ```

2. Or via Docker:

```bash
# Build and run with Docker, then follow logs
docker compose up --build -d && docker compose logs -f
```

### Tracking and Viewing Logs

1. Log files are created in the backend directory:
   - `debug.log` - Contains all debug-level and above messages
   - `error.log` - Contains only error-level messages

2. Monitor logs in real-time using the terminal:
   ```bash
   # Follow the debug log in real-time
   tail -f debug.log

   # Follow only error logs
   tail -f error.log
   ```

### Customizing Logging

Logging is configured in `utils/logging_config.py`:
- The file handles log rotation automatically
- Adjust log levels and formats by modifying the Python configuration
- The default format shows: `[timestamp] [level] [module] message`
- Default log level is set to `INFO` unless overridden by the `LOG_LEVEL` environment variable

## Running with Docker

The backend can be easily run using Docker. This approach ensures consistency across different development environments and simplifies the setup process.

### Prerequisites

- Docker installed on your system
- Docker Compose installed on your system

### Running the Backend with Docker

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Build and start the container in detached mode:
   ```bash
   docker compose up --build -d
   ```

   This command:
   - Builds the Docker image defined in the Dockerfile
   - Creates and starts the container in the background
   - Uses the environment variables from .dev.env
   - Exposes the backend on port 8000

3. View the logs (optional):
   ```bash
   docker compose logs -f
   ```

   The `-f` flag follows the log output in real-time. Press Ctrl+C to stop following the logs.

4. Your backend API is now available at:
   ```
   http://localhost:8000
   ```

### Managing the Container

- To stop the container:
  ```bash
  docker compose down
  ```

- To restart the container:
  ```bash
  docker compose restart
  ```

- To rebuild and restart (after code changes):
  ```bash
  docker compose up --build -d
  ```

### Notes

- The backend runs on port 8000 by default, matching the behavior of running with uvicorn directly
- The container uses the same environment variables from .dev.env as the local development setup
- Any changes to the code will require rebuilding the container

## Additional Resources

- [Full Backend Setup Documentation](https://docs.omi.me/developer/backend/Backend_Setup)
- [Omi Documentation](https://docs.omi.me/)
- [Community Support](https://discord.gg/omi)
