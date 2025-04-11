# Omi Backend Setup

This README provides a quick setup guide for the Omi backend. For a comprehensive step-by-step guide with detailed explanations, please refer to the [Backend Setup Documentation](https://docs.omi.me/docs/developer/backend/Backend_Setup).

## Quick Setup Steps

1. Install the google-cloud-sdk
   - Mac: `brew install google-cloud-sdk`
   - Windows: `choco install gcloudsdk`
   - Nix envdir: It should be pre-installed

2. You will need to have your own Google Cloud Project (please refer to the [App Docs]([url](https://docs.omi.me/docs/developer/AppSetup#7-setup-firebase)) on how to setup Firebase). If you did setup Firebase for the App, then you'll already have a Project in Google Cloud.
 Make sure you have the `Cloud Resource Manager` and `Firebase Management API` permissions at the minimum in the [Google Cloud API Console](https://console.cloud.google.com/apis/dashboard)

3. Run the following commands one by one
	```
	gcloud auth login
	gcloud config set project <project-id>
	gcloud auth application-default login --project <project-id>
	```
	Replace `<project-id>` with your Google Cloud Project ID

	This should generate the `application_default_credentials.json` file in the `~/.config/gcloud` directory.

4. **Important**: In your `.env` file, set the `GOOGLE_APPLICATION_CREDENTIALS` to the absolute path of your credentials file:
   ```
   # For macOS/Linux users (replace 'username' with your actual username)
   GOOGLE_APPLICATION_CREDENTIALS=/Users/username/.config/gcloud/application_default_credentials.json

   # For Windows users (replace 'Username' with your actual username)
   GOOGLE_APPLICATION_CREDENTIALS=C:\Users\Username\.config\gcloud\application_default_credentials.json
   ```
   Do not use the tilde (~) in the path as it may not be properly expanded.

   Also, make sure to set your `GOOGLE_CLOUD_PROJECT` environment variable to your Google Cloud Project ID:
   ```
   GOOGLE_CLOUD_PROJECT=your-project-id
   ```
   This is required for Firebase authentication to work properly.

5. Install Python (use brew if on mac) (or with nix env it will be done for you)
6. Install `pip` (if it doesn't exist)
7. Install `git `and `ffmpeg` (use brew if on mac) (again nix env installs this for you)
8. Move to the backend directory (`cd backend`)
9. Run the command `cat .env.template > .env`
10. For Redis (you can use [upstash](https://upstash.com/), sign up and create a free instance)
11. Add the necessary keys in the env file (OpenAI, Deepgram, Redis, set ADMIN_KEY to 123)
12.  Run the command `pip install -r requirements.txt` to install required dependencies
13. Sign Up on [ngrok](https://ngrok.com/) and follow the steps to configure it
14. During the onboarding flow, under the `Static Domain` section, Ngrok should provide you with a static domain and a command to point your localhost to that static domain. Replace the port from 80 to 8000 in that command and run it in your terminal
	```
	ngrok http --domain=example.ngrok-free.app 8000
	```
15. Run the following command to start the server
	```
	uvicorn main:app --reload --env-file .env
	```
16. If you get any error mentioning `no internet connection or something while downloading models`, then add the following lines in the `utils/stt/vad.py` file after the import statements.
	```
	import ssl
	ssl._create_default_https_context = ssl._create_unverified_context
	```
17. Now try running the `uvicorn main:app --reload --env-file .env` command again.
18. Assign the url given by ngrok in the app's env to `API_BASE_URL`
19. Now your app should be using your local backend

20. If you used a virtual environment, when you're done, deactivate it by running:
    ```bash
    deactivate
    ```

## Docker Setup

If you prefer to run the backend using Docker, follow these steps:

1. Make sure you have Docker installed on your system:
   - Mac: Install Docker Desktop
   - Windows: Install Docker Desktop
   - Linux: Follow the [official Docker installation guide](https://docs.docker.com/engine/install/)

2. Set up your Google Cloud credentials as described in steps 1-3 above.

3. Create a `.env` file in the backend directory by copying the template:
   ```bash
   cat .env.template > .env
   ```

4. Update the `.env` file with your API keys and credentials. For the Google credentials, set:
   ```
   GOOGLE_APPLICATION_CREDENTIALS=google-credentials.json
   ```

5. Copy your Google Cloud application default credentials file to the backend directory:
   ```bash
   cp ~/.config/gcloud/application_default_credentials.json ./google-credentials.json
   ```

6. Make sure your Google Cloud application default credentials file exists:
   ```bash
   cp ~/.config/gcloud/application_default_credentials.json ./google-credentials.json
   ```

7. Build the Docker image:
   ```bash
   docker build -t omi-backend .
   ```

8. Run the container using Docker Compose:
   ```bash
   docker compose up -d
   ```

9. To view logs:
   ```bash
   docker compose logs -f
   ```

10. To stop the container:
    ```bash
    docker compose down
    ```

11. Set up ngrok as described in steps 13-14 above, but point it to port 8000:
    ```bash
    ngrok http --domain=example.ngrok-free.app 8000
    ```

12. Assign the URL given by ngrok in the app's env to `API_BASE_URL`

## Additional Resources

- [Full Backend Setup Documentation](https://docs.omi.me/developer/backend/Backend_Setup)
- [Omi Documentation](https://docs.omi.me/)
- [Community Support](https://discord.gg/omi)
## Troubleshooting

### Opus Library Issues

If you encounter an error related to the opus library like `Exception: Could not find Opus library. Make sure it is installed.`, follow these steps:

1. Make sure you have installed the opus library at the system level:
   ```bash
   # On macOS
   brew install opus

   # On Ubuntu/Debian
   sudo apt-get install libopus-dev
   ```

2. Create a symbolic link to the opus library in your virtual environment:
   ```bash
   # On macOS
   # First, find where the library is installed
   find /usr -name "libopus.dylib" 2>/dev/null || find /opt -name "libopus.dylib" 2>/dev/null

   # Then create a symbolic link (replace the path with your actual path)
   mkdir -p venv/lib
   ln -sf /opt/homebrew/lib/libopus.dylib venv/lib/libopus.dylib

   # Then create a symbolic link (replace the path with your actual path)
   mkdir -p venv/lib
   ln -sf /usr/lib/x86_64-linux-gnu/libopus.so venv/lib/libopus.so
   ```

3. Verify that the opuslib module can now be imported correctly:
   ```bash
   source venv/bin/activate
   python -c "import opuslib; print('opuslib imported successfully')"
   ```

### GitHub API Rate Limits

If you encounter GitHub API rate limit errors, make sure to set the `GITHUB_TOKEN` environment variable in your `.env` file. This will increase your rate limits for GitHub API requests.

### Typesense Configuration

If you want to use Typesense for search functionality:

1. Sign up for [Typesense Cloud](https://cloud.typesense.org/) or [self-host Typesense](https://typesense.org/docs/guide/install-typesense.html)

2. Get your Typesense API key, host, and port:

   **For Typesense Cloud:**
   - After creating a cluster, go to the "API Keys" section
   - Use the "Search Only API Key" or "Admin API Key" depending on your needs
   - For the host, use the hostname shown in the "Cluster Overview" (e.g., `xxx.a1.typesense.net`)
   - For the port, use `443` for HTTPS connections

   **For Self-hosted Typesense:**
   - The API key is the one you specified when starting the Typesense server (with `--api-key`)
   - For the host, use the server's hostname or IP address (e.g., `localhost` or `192.168.1.100`)
   - For the port, use the port you configured when starting the server (default is `8108`)

3. Update your `.env` file with these values:
   ```
   TYPESENSE_HOST=your-typesense-host
   TYPESENSE_HOST_PORT=your-typesense-port
   TYPESENSE_API_KEY=your-typesense-api-key
   ```

   Example for Typesense Cloud:
   ```
   TYPESENSE_HOST=xyz123.a1.typesense.net
   TYPESENSE_HOST_PORT=443
   TYPESENSE_API_KEY=xyzABC123...
   ```

   Example for self-hosted Typesense:
   ```
   TYPESENSE_HOST=localhost
   TYPESENSE_HOST_PORT=8108
   TYPESENSE_API_KEY=xyz123...
   ```

If you don't configure Typesense, a mock client will be used for development, which will return empty search results.

### Silero VAD Model Issues

If you encounter an error like `HTTP Error 401: Unauthorized` or `HTTP Error 404: Not Found` when loading the Silero VAD model, there are several solutions:

1. **The package is already included in requirements.txt:**
   The `silero-vad>=5.1.0` package is already included in the project's requirements.txt file, so it should be installed when you run:
   ```bash
   pip install -r requirements.txt
   ```
   If you need to install it separately or update it:
   ```bash
   # Activate your virtual environment (if not already activated)
   source venv/bin/activate

   # Install or update the Silero VAD package
   pip install silero-vad==5.1.2
   ```

2. **Manual download of model files:**
   If you prefer to download the model files manually:
   ```bash
   # Create the model directory
   mkdir -p pretrained_models/silero_vad

   # Download the model files
   curl -L https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx -o pretrained_models/silero_vad/model.onnx
   ```

The application is configured to fall back to a mock implementation if the model fails to load, but this will limit voice activity detection functionality.

### PyOgg Import Issues

If you encounter an error like `NameError: name 'c_int_p' is not defined` when starting the server, it's due to an issue with the PyOgg library. The application has been updated to handle this error gracefully with a fallback mechanism, but Opus codec functionality will be limited.

To fix the PyOgg library directly:

1. Open the PyOgg opus.py file:
   ```bash
   # Find the file location
   find venv -name opus.py
   ```

2. Edit the file to add the missing POINTER import and replace c_int_p with POINTER(c_int):
   ```python
   # Add this import at the top with other ctypes imports
   from ctypes import POINTER

   # Then replace all instances of c_int_p with POINTER(c_int)
   ```

3. Alternatively, you can use the following Python script to fix it automatically:
   ```python
   file_path = 'venv/lib/python3.10/site-packages/pyogg/opus.py'  # Adjust path as needed

   with open(file_path, 'r') as f:
       content = f.read()

   # Add the missing import
   if 'from ctypes import POINTER' not in content:
       import re
       content = re.sub(
           r'from ctypes import.*?(?=\n)',
           r'\g<0>, POINTER',
           content,
           count=1,
           flags=re.DOTALL
       )

   # Replace c_int_p with POINTER(c_int)
   content = content.replace('c_int_p', 'POINTER(c_int)')

   with open(file_path, 'w') as f:
       f.write(content)
   ```

## Environment Variables Structure

The backend environment variables are now organized into **required** and **optional** categories to simplify setup:

### Required Environment Variables

These variables are essential for core functionality:

1. **Firebase/Google Cloud Authentication**
   ```
   GOOGLE_APPLICATION_CREDENTIALS=google-credentials.json
   GOOGLE_CLOUD_PROJECT=your-project-id
   ```
   These are required for user authentication and database access.

2. **Database Connection (Redis)**
   ```
   REDIS_DB_HOST=your-redis-host
   REDIS_DB_PORT=your-redis-port
   REDIS_DB_PASSWORD=your-redis-password
   ```
   Redis is used for caching and temporary data storage.

3. **API Keys for Core Services**
   ```
   OPENAI_API_KEY=your-openai-api-key
   DEEPGRAM_API_KEY=your-deepgram-api-key
   ADMIN_KEY=your-admin-key
   ```
   These keys enable core functionality like chat, transcription, and admin access.

4. **Base API URL**
   ```
   BASE_API_URL=your-api-base-url
   ```
   This is the URL where your backend can be accessed, used for callbacks and client connections.

### Optional Environment Variables

These variables enable additional features but are not required for core functionality:

1. **Vector Search and Embeddings (Pinecone)**
   ```
   PINECONE_API_KEY=your-pinecone-api-key
   PINECONE_INDEX_NAME=your-pinecone-index-name
   ```
   Used for advanced memory retrieval and search features. If not provided, a local mock implementation will be used.

2. **Full-Text Search (Typesense)**
   ```
   TYPESENSE_HOST=your-typesense-host
   TYPESENSE_HOST_PORT=your-typesense-port
   TYPESENSE_API_KEY=your-typesense-api-key
   ```
   Enables advanced conversation search features. If not configured, a mock implementation will return empty search results.

3. **Google Cloud Storage**
   ```
   BUCKET_SPEECH_PROFILES=your-speech-profiles-bucket-name
   BUCKET_BACKUPS=your-backups-bucket-name
   BUCKET_PLUGINS_LOGOS=your-plugins-logos-bucket-name
   ```
   Used for storing various files. If not configured, local file storage will be used as a fallback.

4. **Additional AI Services**
   ```
   HUGGINGFACE_TOKEN=your-huggingface-token
   SONIOX_API_KEY=your-soniox-api-key
   HUME_API_KEY=your-hume-api-key
   HUME_CALLBACK_URL=your-hume-callback-url
   ```
   Provides additional AI capabilities. Mock implementations will be used if not configured.

5. **Integration Services**
   ```
   GITHUB_TOKEN=your-github-token
   WORKFLOW_API_KEY=your-workflow-api-key
   ```
   Used for external integrations.

6. **Payment Processing**
   ```
   STRIPE_API_KEY=your-stripe-api-key
   STRIPE_WEBHOOK_SECRET=your-stripe-webhook-secret
   STRIPE_CONNECT_WEBHOOK_SECRET=your-stripe-connect-webhook-secret
   ```
   Required only if you need to process payments.

The system is designed to work with just the required variables, with graceful fallbacks for optional services. This makes development and testing much easier, especially when you don't need all the optional services.
