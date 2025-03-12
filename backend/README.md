# Setup
1. Install the google-cloud-sdk `brew install google-cloud-sdk` or if you use nix envdir, it should be installed for you

2. You will need to have your own Google Cloud Project (please refer to the [App Docs]([url](https://docs.omi.me/docs/developer/AppSetup#7-setup-firebase)) on how to setup Firebase). If you did setup Firebase for the App, then you'll already have a Project in Google Cloud.
 Make sure you have the `Cloud Resource Manager` and `Firebase Management API` permissions at the minimum in the [Google Cloud API Console](https://console.cloud.google.com/apis/dashboard)
3. Run the following commands one by one
	```
	gcloud auth login
	gcloud config set project <project-id>
	gcloud auth application-default login --project <project-id>
	```
	Replace `<project-id>` with your Google Cloud Project ID
	This should generate the `application_default_credentials.json` file in the `~/.config/gcloud` directory. This file is read automatically by gcloud in Python, so you don't have to manually add any env for the service account.
5. Install Python (use brew if on mac) (or with nix env it will be done for you)
6. Install `pip` (if it doesn't exist)
7. Install `git `and `ffmpeg` (use brew if on mac) (again nix env installs this for you)
8. Move to the backend directory (`cd backend`)
9. Run the command `cat .env.template > .env`
10. For Redis (you can use [upstash](https://upstash.com/), sign up and create a free instance)
11. Add the necessary API keys in the `.env` file:
    - [OpenAI API Key](https://platform.openai.com/settings/organization/api-keys)
    - [Deepgram API Key](https://console.deepgram.com/api-keys)
    - Redis credentials from your [Upstash Console](https://console.upstash.com/)
    - Set `ADMIN_KEY` to a temporary value (e.g., `123`) for local development
    - **IMPORTANT:** For Pinecone vector database:
      - Make sure to set `PINECONE_INDEX_NAME` to the name of your Pinecone index
      - If you don't have a Pinecone index yet, [create one in the Pinecone Console](https://app.pinecone.io/)
      - The index should be created with the appropriate dimension setting (e.g., 1536 for OpenAI embeddings)
    - **Optional:** For Typesense search functionality:
      - Set `TYPESENSE_HOST`, `TYPESENSE_HOST_PORT`, and `TYPESENSE_API_KEY` if you want to use Typesense
      - If not set, a mock client will be used for development
      - You can [sign up for Typesense Cloud](https://cloud.typesense.org/) or [self-host it](https://typesense.org/docs/guide/install-typesense.html)
    - **Optional but recommended:** Set `GITHUB_TOKEN` to a [GitHub personal access token](https://github.com/settings/tokens)
      - This is used to access GitHub's API for retrieving firmware updates and documentation
      - Without this token, GitHub API requests will have lower rate limits
      - You can create a token with `public_repo` scope only
      - [Generate a new token here](https://github.com/settings/tokens/new?scopes=public_repo&description=Omi%20Backend%20Access)
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
