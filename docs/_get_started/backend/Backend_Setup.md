---
layout: default
title: Backend Setup
parent: Backend
nav_order: 1
---

# Omi Backend Setup Guide 🚀

Welcome to the in-depth Omi backend setup guide! This document provides a comprehensive walkthrough for setting up and running the Omi backend, which powers the intelligent capabilities of our multimodal AI assistant. Whether you're a seasoned developer or new to the project, this guide will help you get the backend up and running smoothly.

## Table of Contents

1. [Prerequisites](#prerequisites-)
2. [Setting Up Google Cloud & Firebase](#i-setting-up-google-cloud--firebase-)
3. [Backend Setup](#ii-backend-setup-)
4. [Running the Backend Locally](#iii-running-the-backend-locally-)
5. [Environment Variables](#environment-variables-)
6. [Modal Serverless Deployment](#modal-serverless-deployment-)
7. [Comprehensive Troubleshooting Guide](#comprehensive-troubleshooting-guide-)
8. [Performance Optimization](#performance-optimization-)
9. [Security Considerations](#security-considerations-)
10. [Contributing](#contributing-)
11. [Support](#support-)

## Prerequisites 📋

Before you begin, ensure you have the following:

- **Google Cloud Project:** With Firebase enabled. If you've set up Firebase for the Omi app, you already have this.

- **API Keys:**

  - **Required API Keys:**
    - **OpenAI:** [platform.openai.com](https://platform.openai.com/) - For language models and embeddings
    - **Deepgram:** [deepgram.com](https://deepgram.com/) - For real-time speech-to-text
    - **Redis:** Upstash recommended [upstash.com](https://upstash.com/) - For caching and temporary data storage
    - **Pinecone:** Use "text-embedding-ada-002" model [pinecone.io](https://www.pinecone.io/) - For vector database operations
    - **Hugging Face:** [huggingface.co](https://huggingface.co/) - For voice activity detection models

  - **Optional API Keys:**
    - **Modal:** [modal.com](https://modal.com/) - For serverless deployment
    - **GitHub:** [github.com](https://github.com/) - For firmware updates
    - **Hume AI:** [hume.ai](https://hume.ai/) - For emotional analysis (optional)
    - **Google Maps API Key:** 🗺️ For location features

- **Development Environment:**
  - **Python 3.9 or higher** (Python 3.11 recommended)
  - **pip** (latest version)
  - **git**
  - **ffmpeg** (for audio processing)
  - **Ngrok** (for tunneling localhost)
  - **A code editor** (e.g., VSCode, PyCharm)

- **Installation Guides:**
  - [Python Installation Guide](https://www.python.org/downloads/)
  - [ffmpeg Installation Guide](https://ffmpeg.org/download.html)
  - [git Installation Guide](https://git-scm.com/downloads)
  - [Ngrok Installation Guide](https://ngrok.com/download)

## I. Setting Up Google Cloud & Firebase ☁️

1. **Install Google Cloud SDK:**

   - **macOS (using Homebrew):**

     ```bash
     brew install google-cloud-sdk
     ```

   - **Ubuntu/Debian:**

     ```bash
     sudo apt-get install apt-transport-https ca-certificates gnupg
     echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] \
     https://packages.cloud.google.com/apt cloud-sdk main" | \
     sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list
     sudo apt-get update && sudo apt-get install google-cloud-sdk
     ```

   - **Windows:**
     - Download and install from the [official Google Cloud SDK installation guide](https://cloud.google.com/sdk/docs/install#windows).

2. **Enable Necessary APIs:**

   - Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
   - Select your project.
   - Go to **APIs & Services** -> **Library**.
   - Search for and enable these APIs:
     - **Cloud Resource Manager API**
     - **Firebase Management API**
     - **Cloud Storage API**
     - **Cloud Firestore API**

3. **Authenticate with Google Cloud:**

   ```bash
   gcloud auth login
   gcloud config set project <project-id>
   gcloud auth application-default login
   ```

   - Replace `<project-id>` with your actual Google Cloud project ID.
   - This generates `application_default_credentials.json` in `~/.config/gcloud` (macOS/Linux) or `%APPDATA%\gcloud` (Windows).

   **Note:** If you encounter any permission issues, ensure your Google account has the necessary roles (e.g., **Project Owner**, **Firebase Admin**) in the Google Cloud Console.

   - To assign roles:
     - Go to **IAM & Admin** -> **IAM**.
     - Locate your account and ensure it has the required permissions.

## II. Backend Setup 🛠️

1. **Install Python & Dependencies:**

   - **macOS (using Homebrew):**

     ```bash
     brew install python@3.11 git ffmpeg
     ```

   - **Ubuntu/Debian:**

     ```bash
     sudo apt-get update
     sudo apt-get install python3.11 python3-pip git ffmpeg
     ```

   - **Windows:**

     - Download and install:
       - [Python Installer](https://www.python.org/downloads/windows/)
         - Ensure you check **Add Python to PATH** during installation.
       - [Git for Windows](https://gitforwindows.org/)
       - [FFmpeg Builds](https://www.gyan.dev/ffmpeg/builds/)

   **Verify Installations:**

   ```bash
   python --version
   git --version
   ffmpeg -version
   ```

2. **Clone the Backend Repository:**

   ```bash
   git clone https://github.com/BasedHardware/Omi.git
   cd Omi/backend
   ```

3. **Set up a Virtual Environment (Recommended):**

   ```bash
   # Create a virtual environment
   python3 -m venv omi_env

   # Activate the virtual environment
   # On macOS/Linux:
   source omi_env/bin/activate
   # On Windows:
   omi_env\Scripts\activate
   ```

4. **Set up the Environment File:**

   ```bash
   # Copy the template and edit the .env file
   cp .env.template .env
   # Use a text editor to fill in your API keys and settings
   nano .env  # Or your preferred editor
   ```

   **Important:** Never commit your `.env` file to version control. It's added to `.gitignore` by default.

   - **Security Reminder:**
     - Keep your API keys and secrets secure.
     - Consider using tools like `dotenv` to manage environment variables.

5. **Install Python Dependencies:**

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

   - If you encounter issues, try:

     ```bash
     pip install -r requirements.txt --no-cache-dir
     ```

   - **Troubleshooting:**
     - Install dependencies individually to identify any problematic packages.

## III. Running the Backend Locally 🏃‍♂️

1. **Set up Ngrok for Tunneling:**

   - Sign up at [ngrok.com](https://ngrok.com/) and install Ngrok.
   - Authenticate Ngrok with your account:

     ```bash
     ngrok authtoken <your-auth-token>
     ```

   - Start an Ngrok tunnel to your localhost:

     ```bash
     ngrok http 8000
     ```

   **Note:** For custom domains using the `--domain` flag, a paid Ngrok plan is required.

2. **Start the Backend Server:**

   ```bash
   uvicorn main:app --reload --env-file .env --host 0.0.0.0 --port 8000
   ```

   - `--reload`: Automatically restarts the server when code changes are detected.
   - `--env-file .env`: Loads environment variables from the `.env` file.
   - `--host 0.0.0.0`: Allows external access to the server.
   - `--port 8000`: Specifies the port to run the server on.

3. **Verify the Server:**

   - Open a web browser and navigate to `http://localhost:8000/docs`.
   - Alternatively, use the Ngrok URL provided (e.g., `https://<your-ngrok-id>.ngrok.io/docs`).
   - You should see the Swagger UI documentation for the API.

4. **Connect the App to the Backend:**

   - In your Omi app's configuration, set `API_BASE_URL` to the Ngrok URL:

     ```env
     API_BASE_URL=https://<your-ngrok-id>.ngrok.io
     ```

   - Replace `<your-ngrok-id>` with the forwarding address displayed by Ngrok.

## Environment Variables 🔐

Detailed explanation of each variable in your `.env` file:

- `HUGGINGFACE_TOKEN`: Your Hugging Face API token for downloading speech processing models.
- `BUCKET_SPEECH_PROFILES`: Name of the Google Cloud Storage bucket for storing user speech profiles.
- `BUCKET_BACKUPS`: Name of the Google Cloud Storage bucket for backups (if applicable).
- `GOOGLE_APPLICATION_CREDENTIALS`: Full path to your Google Cloud credentials JSON file.

  - Example paths:
    - macOS/Linux: `/Users/yourname/.config/gcloud/application_default_credentials.json`
    - Windows: `C:\Users\yourname\AppData\Roaming\gcloud\application_default_credentials.json`

- `PINECONE_API_KEY`: Your Pinecone API key for vector database operations.
- `PINECONE_INDEX_NAME`: Name of your Pinecone index (create this in the Pinecone console).
- `REDIS_DB_HOST`: Hostname of your Redis instance (e.g., `redis-12345.c56.us-east-1-3.ec2.cloud.redislabs.com`).
- `REDIS_DB_PORT`: Port number for your Redis instance (usually 6379).
- `REDIS_DB_PASSWORD`: Password for your Redis instance.
- `DEEPGRAM_API_KEY`: Your Deepgram API key for real-time and pre-recorded audio transcription.
- `ADMIN_KEY`: A secure key for admin-level API access (generate a strong, random string).
- `OPENAI_API_KEY`: Your OpenAI API key for accessing language models and embeddings.
- `GITHUB_TOKEN`: Your GitHub personal access token (if using GitHub for firmware updates).
- `WORKFLOW_API_KEY`: Custom API key for securing communication with external workflows.
- `HUME_API_KEY`: Your Hume AI API key for emotional analysis features (if enabled).

**Important:** Never commit your `.env` file to version control. Ensure it's listed in your `.gitignore`:

```gitignore
# .gitignore

# Ignore environment files
.env
*.env

# Ignore virtual environments
venv/
omi_env/

# Ignore Python cache files
__pycache__/
*.pyc
```

## Modal Serverless Deployment 🚀

For deploying the backend using Modal:

1. **Install Modal:**

   ```bash
   pip install modal
   ```

2. **Set up Modal Secrets:**

   - Use Modal's CLI or dashboard to create secrets for your environment variables.

     ```bash
     # Create secret for Google Cloud credentials
     modal secret create gcp-credentials --from-file application_default_credentials.json

     # Create secret for environment variables
     modal secret create envs --from-env-file .env
     ```

   - Ensure you securely store all necessary credentials and environment variables.

3. **Prepare for Deployment:**

   - Update your `main.py` to include Modal configurations:

     ```python
     # main.py
     import modal

     stub = modal.Stub("omi-backend")

     image = modal.Image.debian_slim().pip_install_from_requirements("requirements.txt")

     @stub.function(image=image, secrets=[modal.Secret.from_name("gcp-credentials"), modal.Secret.from_name("envs")])
     @modal.asgi_app()
     def fastapi_app():
         from main import app
         return app
     ```

   - Ensure that `main.py` properly imports your FastAPI app and any necessary modules.

4. **Deploy to Modal:**

   ```bash
   modal deploy main.py
   ```

5. **Verify Deployment:**

   - Modal will provide a URL for your deployed app.
   - Visit `https://<modal-url>/docs` to ensure the API is accessible.
   - Update your Omi app's `API_BASE_URL` to point to the Modal URL.

## Comprehensive Troubleshooting Guide 🔧

### Common Issues and Solutions:

#### 1. SSL Certificate Errors

If you encounter SSL certificate errors when downloading models:

- **Temporary Workaround:**

  ```python
  # Add at the top of your script
  import ssl
  ssl._create_default_https_context = ssl._create_unverified_context
  ```

- **Permanent Solution:**

  - Update your SSL certificates or configure your environment to trust the necessary certificates.
  - Avoid disabling SSL verification in production environments due to security risks.

#### 2. API Key Issues

- **Steps to Resolve:**

  - Double-check all API keys in your `.env` file for accuracy.
  - Ensure there are no extra spaces or hidden characters.
  - Confirm that your API keys have the necessary permissions and are active.

#### 3. Ngrok Connection Problems

- **Troubleshooting Tips:**

  - Ensure Ngrok is running and the tunnel is active.
  - Verify the Ngrok URL is correctly set in the Omi app's `API_BASE_URL`.
  - Check Ngrok's console for any error messages or warnings.
  - Ensure your firewall allows traffic on the required ports.

#### 4. Dependency Installation Failures

- **Possible Solutions:**

  - Upgrade pip:

    ```bash
    pip install --upgrade pip
    ```

  - Install dependencies without cache:

    ```bash
    pip install -r requirements.txt --no-cache-dir
    ```

  - Install dependencies one by one to identify the problematic package.

#### 5. Database Connection Errors

- **Firestore:**

  - Verify that Firestore is enabled in your Google Cloud project.
  - Ensure your service account has the **Cloud Datastore User** role.

- **Redis:**

  - Check your Redis connection settings.
  - Ensure your IP is whitelisted in Redis (if using Upstash).

#### 6. "Module Not Found" Errors

- **Solutions:**

  - Ensure you're in the correct virtual environment.
  - Reinstall the missing module:

    ```bash
    pip install <module-name>
    ```

#### 7. Performance Issues

- **Recommendations:**

  - Monitor your API usage and quotas for third-party services.
  - Implement caching strategies for frequently accessed data.
  - Use profiling tools to identify bottlenecks in your code.

#### 8. Firewall and Network Issues

- **Check:**

  - Ensure your firewall allows traffic on ports 8000 (backend) and the Ngrok assigned port.
  - Verify network settings if running in a corporate or restricted environment.

#### 9. Python Version Conflicts

- **Resolution:**

  - Ensure you're using the correct Python version (3.9 or higher).
  - Use `python3` explicitly if multiple versions are installed.

## Performance Optimization 🚀

1. **Caching Strategy:**

   - Implement Redis caching for frequently accessed data.
   - Example using `redis`:

     ```python
     import redis

     r = redis.Redis(host='localhost', port=6379, db=0)

     @app.get("/data")
     async def get_data():
         cached_data = r.get("data_key")
         if cached_data:
             return json.loads(cached_data)
         data = await fetch_data_from_db()
         r.set("data_key", json.dumps(data), ex=3600)  # Cache for 1 hour
         return data
     ```

2. **Asynchronous Operations:**

   - Utilize FastAPI's async features for I/O-bound operations.
   - Use `asyncio` for concurrent tasks.

3. **Database Optimization:**

   - Design efficient Firestore queries and proper indexing.
   - Use batch operations for multiple writes.

4. **API Rate Limiting:**

   - Implement rate limiting to prevent abuse using middleware or extensions like `slowapi`.

     ```python
     from slowapi import Limiter, _rate_limit_exceeded_handler
     from slowapi.util import get_remote_address

     limiter = Limiter(key_func=get_remote_address)
     app.state.limiter = limiter
     app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

     @app.get("/endpoint")
     @limiter.limit("5/minute")
     async def limited_endpoint():
         return {"message": "This endpoint is rate limited."}
     ```

5. **Monitoring and Profiling:**

   - Integrate tools like **Prometheus** and **Grafana** for monitoring.
   - Use Python profiling tools like `cProfile` or third-party services like **New Relic**.

## Security Considerations 🔒

1. **API Security:**

   - Implement authentication and authorization mechanisms (e.g., OAuth 2.0, JWT).
   - Use HTTPS for all communications.
   - Regularly rotate API keys and secrets.

2. **Data Protection:**

   - Encrypt sensitive data at rest and in transit.
   - Apply proper access controls in Firestore and Google Cloud Storage.
   - Regularly back up data and test restoration procedures.

3. **Dependency Management:**

   - Regularly update dependencies to patch security vulnerabilities.
   - Use tools like `safety` and `bandit` to check for known vulnerabilities:

     ```bash
     pip install safety bandit
     safety check
     bandit -r .
     ```

4. **Environment Isolation:**

   - Use separate environments for development, staging, and production.
   - Apply appropriate access controls and configurations for each environment.

5. **Audit Logging:**

   - Implement comprehensive logging for security-relevant events.
   - Use centralized logging solutions for analysis (e.g., ELK Stack).

6. **Data Compliance:**

   - Be aware of data protection laws (e.g., GDPR, CCPA).
   - Implement user consent mechanisms and data handling policies.

## Contributing 🤝

We welcome contributions! Check our [Contribution Guide](https://docs.omi.me/developer/Contribution/) for details on:

- Setting up a development environment
- Coding standards and best practices (e.g., following [PEP 8](https://www.python.org/dev/peps/pep-0008/) for Python code)
- Writing tests to ensure code quality
- Pull request process
- Code review guidelines

**Note:** Ensure the link to the contribution guide is correct and accessible.

## Support 🆘

If you need help:

- **GitHub Issues:** 🐛 For bug reports and feature requests
- **Community Forum:** 💬 Join our [Discord community](https://discord.gg/ZutWMTJnwA)
- **Documentation:** 📚 Visit our [full documentation](https://docs.omi.me/)
- **FAQ:** Check our [Frequently Asked Questions](https://docs.omi.me/faq/) section in the docs
- **Email Support:** ✉️ Contact us at [support@omi.me](mailto:support@omi.me)

Remember, when seeking help, provide as much relevant information as possible, including error messages, logs, and steps to reproduce the issue.

---

Happy coding! 💻 Don't hesitate to reach out if you need assistance. The Omi community is here to help you succeed in building amazing AI-powered experiences.

