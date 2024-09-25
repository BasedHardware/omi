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
- **API Keys:** 🔑
  - OpenAI: [platform.openai.com](https://platform.openai.com/) - For language models and embeddings
  - Deepgram: [deepgram.com](https://deepgram.com/) - For real-time speech-to-text
  - Redis: Upstash recommended [upstash.com](https://upstash.com/) - For caching and temporary data storage
  - Pinecone: Use "text-embedding-3-large" model [pinecone.io](https://www.pinecone.io/) - For vector database operations
  - Modal: (Optional) [modal.com](https://modal.com/) - For serverless deployment
  - Hugging Face: [huggingface.co](https://huggingface.co/) - For voice activity detection models
  - GitHub: (Optional) [github.com](https://github.com/) - For firmware updates
  - Hume AI: [hume.ai](https://hume.ai/) - For emotional analysis (optional)
- **Google Maps API Key:** 🗺️ (Optional) For location features
- **Development Environment:** 
  - Python 3.9+ (3.11 recommended)
  - pip (latest version)
  - git
  - ffmpeg (for audio processing)
  - A code editor (e.g., VSCode, PyCharm)

## I. Setting Up Google Cloud & Firebase ☁️

1. **Install Google Cloud SDK:**
   ```bash
   # Mac (using brew)
   brew install google-cloud-sdk
   
   # Nix Envdir users: The SDK is usually pre-installed
   
   # For other systems, follow the official Google Cloud SDK installation guide
   ```

2. **Enable Necessary APIs:**
   - Navigate to the [Google Cloud Console](https://console.cloud.google.com/)
   - Select your project
   - Go to APIs & Services -> Library
   - Search for and enable these APIs:
     - Cloud Resource Manager API
     - Firebase Management API
     - Cloud Storage API
     - Cloud Firestore API

3. **Authenticate with Google Cloud:**
   ```bash
   gcloud auth login
   gcloud config set project <project-id>
   gcloud auth application-default login --project <project-id>
   ```
   This generates `application_default_credentials.json` in `~/.config/gcloud`.

   **Note:** If you encounter any permission issues, ensure your Google account has the necessary roles (e.g., Project Owner, Firebase Admin) in the Google Cloud Console.

## II. Backend Setup 🛠️

1. **Install Python & Dependencies:**
   ```bash
   # Mac (using brew)
   brew install python@3.11 git ffmpeg
   
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install python3.11 python3-pip git ffmpeg
   
   # Install pip if not present (Mac)
   curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
   python3 get-pip.py
   ```

2. **Clone the Backend Repository:**
   ```bash
   git clone https://github.com/BasedHardware/Omi.git
   cd Omi/backend
   ```

3. **Set up a Virtual Environment (Recommended):**
   ```bash
   python3 -m venv omi_env
   source omi_env/bin/activate  # On Windows, use: omi_env\Scripts\activate
   ```

4. **Set up the Environment File:**
   ```bash
   cp .env.template .env
   ```
   Edit `.env` and fill in all required API keys and settings. See the [Environment Variables](#environment-variables-) section for detailed explanations.

5. **Install Python Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   If you encounter any issues, try:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt --no-cache-dir
   ```

## III. Running the Backend Locally 🏃‍♂️

1. **Set up Ngrok for Tunneling:**
   - Sign up at [ngrok.com](https://ngrok.com/) and install Ngrok
   - Authenticate Ngrok with your account:
     ```bash
     ngrok authtoken <your-auth-token>
     ```
   - Create a tunnel to your localhost:
     ```bash
     ngrok http --domain=example.ngrok-free.app 8000
     ```
   **Note:** Keep the Ngrok terminal window open while developing.

2. **Start the Backend Server:**
   ```bash
   uvicorn main:app --reload --env-file .env --host 0.0.0.0 --port 8000
   ```
   - `--reload`: Automatically restarts the server when code changes are detected
   - `--env-file .env`: Loads environment variables from the .env file
   - `--host 0.0.0.0`: Allows external access to the server
   - `--port 8000`: Specifies the port to run the server on

3. **Verify the Server:**
   Open a web browser and navigate to `http://localhost:8000/docs`. You should see the Swagger UI documentation for the API.

4. **Connect the App to the Backend:**
   - In your Omi app's environment, set `API_BASE_URL` to the Ngrok URL (e.g., `https://example.ngrok-free.app`)

## Environment Variables 🔐

Detailed explanation of each variable in your `.env` file:

- `HUGGINGFACE_TOKEN`: Your Hugging Face API token for downloading speech processing models
- `BUCKET_SPEECH_PROFILES`: Name of the Google Cloud Storage bucket for storing user speech profiles
- `BUCKET_BACKUPS`: Name of the Google Cloud Storage bucket for backups (if applicable)
- `GOOGLE_APPLICATION_CREDENTIALS`: Full path to your Google Cloud credentials JSON file
- `PINECONE_API_KEY`: Your Pinecone API key for vector database operations
- `PINECONE_INDEX_NAME`: Name of your Pinecone index (create this in the Pinecone console)
- `REDIS_DB_HOST`: Hostname of your Redis instance (e.g., `redis-12345.c56.us-east-1-3.ec2.cloud.redislabs.com`)
- `REDIS_DB_PORT`: Port number for your Redis instance (usually 6379)
- `REDIS_DB_PASSWORD`: Password for your Redis instance
- `DEEPGRAM_API_KEY`: Your Deepgram API key for real-time and pre-recorded audio transcription
- `ADMIN_KEY`: A secure key for admin-level API access (generate a strong, random string)
- `OPENAI_API_KEY`: Your OpenAI API key for accessing language models and embeddings
- `GITHUB_TOKEN`: Your GitHub personal access token (if using GitHub for firmware updates)
- `WORKFLOW_API_KEY`: Custom API key for securing communication with external workflows
- `HUME_API_KEY`: Your Hume AI API key for emotional analysis features (if enabled)

**Important:** Never commit your `.env` file to version control. It's added to `.gitignore` by default.

## Modal Serverless Deployment 🚀

For deploying the backend using Modal:

1. **Install Modal:**
   ```bash
   pip install modal
   ```

2. **Set up Modal secrets:**
   ```bash
   modal secret create gcp-credentials
   modal secret create envs
   ```
   Follow the prompts to input your Google Cloud credentials and environment variables.

3. **Prepare for Deployment:**
   Ensure your `main.py` file is configured for Modal deployment. It should include:
   ```python
   from modal import Image, Stub, asgi_app
   
   stub = Stub("omi-backend")
   
   image = Image.debian_slim().pip_install_from_requirements("requirements.txt")
   
   @stub.function(image=image)
   @asgi_app()
   def fastapi_app():
       from main import app
       return app
   ```

4. **Deploy to Modal:**
   ```bash
   modal deploy main.py
   ```

5. **Verify Deployment:**
   Modal will provide a URL for your deployed app. Visit `<modal-url>/docs` to ensure the API is accessible.

## Comprehensive Troubleshooting Guide 🔧

### Common Issues and Solutions:

1. **SSL Certificate Errors:**
   If you encounter SSL certificate errors when downloading models, add this to `utils/stt/vad.py`:
   ```python
   import ssl
   ssl._create_default_https_context = ssl._create_unverified_context
   ```
   **Note:** This is a temporary workaround and should not be used in production.

2. **API Key Issues:**
   - Double-check all API keys in `.env` for accuracy
   - Ensure there are no trailing spaces or quotes around the keys
   - Verify that your API keys have the necessary permissions and are active

3. **Ngrok Connection Problems:**
   - Ensure Ngrok is running and the tunnel is active
   - Verify the Ngrok URL is correctly set in the Omi app's `API_BASE_URL`
   - Check Ngrok's console for any error messages or warnings

4. **Dependency Installation Failures:**
   If you encounter issues installing dependencies:
   ```bash
   pip install -r requirements.txt --upgrade --force-reinstall
   ```
   If problems persist, try installing dependencies one by one to identify the problematic package.

5. **Database Connection Errors:**
   - Verify your Firestore and Redis connection settings
   - Ensure your Google Cloud project has Firestore enabled
   - Check if your IP is whitelisted in Redis (if using Upstash)

6. **"Module Not Found" Errors:**
   - Ensure you're in the correct virtual environment
   - Try reinstalling the specific module:
     ```bash
     pip install <module-name>
     ```

7. **Performance Issues:**
   - Monitor your API usage and quotas for third-party services
   - Consider implementing caching for frequently accessed data
   - Use profiling tools to identify bottlenecks in your code

8. **Firestore Permissions:**
   If you encounter Firestore access issues:
   - Verify that your service account has the "Cloud Datastore User" role
   - Ensure Firestore is initialized in your Google Cloud project

9. **Modal Deployment Issues:**
   - Check that all environment variables are correctly set in Modal secrets
   - Verify that your `main.py` is correctly configured for Modal
   - Review Modal's deployment logs for any specific error messages

### Debugging Tips:

- Use logging extensively throughout your code to track the flow of execution
- Implement try-except blocks to catch and log specific exceptions
- Utilize FastAPI's built-in debugging tools and error handlers
- For complex issues, consider using a debugger like pdb or an IDE's built-in debugger

## Performance Optimization 🚀

1. **Caching Strategy:**
   - Implement Redis caching for frequently accessed data
   - Use Firestore's offline persistence for improved performance

2. **Asynchronous Operations:**
   - Utilize FastAPI's async features for I/O-bound operations
   - Implement background tasks for time-consuming processes

3. **Database Optimization:**
   - Design efficient Firestore queries and indexes
   - Use batch operations for multiple database writes

4. **API Rate Limiting:**
   - Implement rate limiting to prevent abuse and ensure fair usage

5. **Monitoring and Profiling:**
   - Set up logging and monitoring tools (e.g., Prometheus, Grafana)
   - Regularly profile your code to identify and optimize bottlenecks

## Security Considerations 🔒

1. **API Security:**
   - Implement proper authentication and authorization
   - Use HTTPS for all communications
   - Regularly rotate API keys and secrets

2. **Data Protection:**
   - Encrypt sensitive data at rest and in transit
   - Implement proper access controls in Firestore and GCS
   - Regularly backup your data and test restoration procedures

3. **Dependency Management:**
   - Regularly update dependencies to patch security vulnerabilities
   - Use tools like `safety` to check for known vulnerabilities in your dependencies

4. **Environment Isolation:**
   - Use separate environments (development, staging, production) with appropriate access controls

5. **Audit Logging:**
   - Implement comprehensive logging for security-relevant events
   - Regularly review logs for suspicious activities

## Contributing 🤝

We welcome contributions! Check our [Contribution Guide](https://docs.omi.me/developer/Contribution/) for details on:
- Setting up a development environment
- Coding standards and best practices
- Pull request process
- Code review guidelines

## Support 🆘

If you need help:

- **GitHub Issues:** 🐛 For bug reports and feature requests
- **Community Forum:** 💬 Join our [Discord community](https://discord.gg/ZutWMTJnwA)
- **Documentation:** 📚 Visit our [full documentation](https://docs.omi.me/)
- **FAQ:** Check our Frequently Asked Questions section in the docs

Remember, when seeking help, provide as much relevant information as possible, including error messages, logs, and steps to reproduce the issue.

Happy coding! 💻 Don't hesitate to reach out if you need assistance. The Omi community is here to help you succeed in building amazing AI-powered experiences.

