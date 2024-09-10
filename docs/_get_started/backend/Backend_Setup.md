---
layout: default
title: Backend Setup
parent: Backend
nav_order: 1
---

# Backend Setup 🚀

Welcome to the Omi backend setup guide! Omi is an innovative, multimodal AI assistant that combines cutting-edge technologies to provide a seamless user experience. This guide will help you set up the
backend infrastructure that powers Omi's intelligent capabilities.

## Prerequisites 📋

Before you start, make sure you have the following:

- **Google Cloud Project:** You need a Google Cloud project with Firebase enabled. If you've already set up Firebase for the Omi app, you're good to go.
- **API Keys: 🔑**  Obtain API keys for:
    - **OpenAI:** For AI language models ([platform.openai.com](https://platform.openai.com/))
    - **Deepgram:** For speech-to-text ([deepgram.com](https://deepgram.com/))
    - **Redis:** Upstash is recommended ([upstash.com](https://upstash.com/))
    - **Pinecone:** For vector database; use "text-embedding-3-large" model ([pinecone.io](https://www.pinecone.io/))
    - **Modal: [optional]**  For serverless deployment ([modal.com](https://modal.com/))
    - **Hugging Face:** For voice activity detection ([huggingface.co](https://huggingface.co/))
    - **GitHub:[optional]** For firmware updates ([github.com](https://github.com/))
- **Google Maps API Key:** 🗺️ (Optional) For location features

## I. Setting Up Google Cloud & Firebase ☁️

1. **Install Google Cloud SDK:**
    - **Mac (using brew):** `brew install google-cloud-sdk`
    - **Nix Envdir:** The SDK is usually pre-installed

2. **Enable Necessary APIs: 🔧**
    - Go to the [Google Cloud Console](https://console.cloud.google.com/)
    - Select your project
    - Navigate to APIs & Services -> Library
    - Enable the following APIs:
        - Cloud Resource Manager API
        - Firebase Management API

3. **Authenticate with Google Cloud: 🔐**
    - Open your terminal
    - Run the following commands one by one, replacing `<project-id>` with your Google Cloud project ID:
       ```bash
       gcloud auth login
       gcloud config set project <project-id>
       gcloud auth application-default login --project <project-id>
       ```
    - This process generates an `application_default_credentials.json` file in the `~/.config/gcloud` directory. This file is used for automatic authentication with Google Cloud services in Python.

## II. Backend Setup 🛠️

1. **Install Python & Dependencies: 🐍**
    - **Mac (using brew):** `brew install python`
    - **Nix Envdir:** Python is pre-installed
    - **Install pip (if not present):**
        - **Mac:** Use `easy_install pip`
        - **Other Systems:**  Follow instructions on [https://pip.pypa.io/en/stable/installation/](https://pip.pypa.io/en/stable/installation/)
    - **Install Git and FFmpeg:**
        - **Mac (using brew):** `brew install git ffmpeg`
        - **Nix Envdir:** Git and FFmpeg are pre-installed

2. **Clone the Backend Repository: 📂**
    - Open your terminal and navigate to your desired directory
    - Clone the Omi backend repository:
       ```bash
       git clone https://github.com/BasedHardware/Omi.git
       cd Omi
       cd backend 
       ```

3. **Set up the Environment File: 📝**
    - Create a copy of the `.env.template` file and rename it to `.env`:
      ```bash
      cp .env.template .env
      ```
    - Open the `.env` file and fill in the following:
        - **OpenAI API Key:** Obtained from your OpenAI account
        - **Deepgram API Key:** Obtained from your Deepgram account
        - **Redis Credentials:**  Host, port, username, and password for your Redis instance
        - **Modal API Key:**  Obtained from your Modal account
        - **`ADMIN_KEY`:** Set to a temporary value (e.g., `123`) for local development
        - **Other API Keys:** Fill in any other API keys required by your integrations (e.g., Google Maps API key)

4. **Install Python Dependencies: 📚**
    - In your terminal (inside the backend directory), run:
       ```bash
       pip install -r requirements.txt
       ```

## III. Running the Backend Locally 🏃‍♂️

1. **Set up Ngrok for Tunneling: 🚇**
    - Sign up for a free account on [https://ngrok.com/](https://ngrok.com/) and install Ngrok
    - Follow their instructions to authenticate Ngrok with your account
    - During the onboarding, Ngrok will provide you with a command to create a tunnel to your localhost. Modify the port in the command to `8000` (the default port for the backend). For example:
      ```bash
      ngrok http --domain=example.ngrok-free.app 8000 
      ```
    - Run this command in your terminal. Ngrok will provide you with a public URL (like `https://example.ngrok-free.app`) that points to your local backend

2. **Start the Backend Server: 🖥️**
    - In your terminal, run:
      ```bash
      uvicorn main:app --reload --env-file .env 
      ```
        - `--reload` automatically restarts the server when code changes are saved, making development easier
        - `--env-file .env` loads environment variables from your `.env` file
        - `--host 0.0.0.0` listens to every interface on your computer so you don't have to set up `ngrok` when developing in your network
        -  `--port 8000` port for backend to listen

3. **Troubleshooting SSL Errors: 🔒**
    - **SSL Errors:** If you encounter SSL certificate errors during model downloads, add this to `utils/stt/vad.py`:
      ```python
      import ssl
      ssl._create_default_https_context = ssl._create_unverified_context
      ```
    - **API Key Issues:** Double-check all API keys in your `.env` file. Ensure there are no trailing spaces
    - **Ngrok Connection:** Ensure your Ngrok tunnel is active and the URL is correctly set in the Omi app
    - **Dependencies:** If you encounter any module not found errors, try reinstalling dependencies:
      ```bash
      pip install -r requirements.txt --upgrade --force-reinstall
      ```

4. **Connect the App to the Backend: 🔗**
    - In your Omi app's environment variables, set the `API_BASE_URL` to the public URL provided by Ngrok (e.g., `https://example.ngrok-free.app`)

Now, your Omi app should be successfully connected to the locally running backend.

## Environment Variables 🔐

Here's a detailed explanation of each environment variable you need to define in your `.env` file:

- **`HUGGINGFACE_TOKEN`:** Your Hugging Face Hub API token, used to download models for speech processing (like voice activity detection)
- **`BUCKET_SPEECH_PROFILES`:**  The name of the Google Cloud Storage bucket where user speech profiles are stored
- **`BUCKET_BACKUPS`:** The name of the Google Cloud Storage bucket used for backups (if applicable)
- **`GOOGLE_APPLICATION_CREDENTIALS`:**  The path to your Google Cloud service account credentials file (`google-credentials.json`). This file is generated in step 3 of **I. Setting Up Google Cloud &
  Firebase**
- **`PINECONE_API_KEY`:** Your Pinecone API key, used for vector database operations. Storing Memory Embeddings: Each memory is converted into a numerical representation (embedding). Pinecone
  efficiently stores these embeddings and allows Omi to quickly find the most relevant memories related to a user's query
- **`PINECONE_INDEX_NAME`:** The name of your Pinecone index where memory embeddings are stored
- **`REDIS_DB_HOST`:** The host address of your Redis instance
- **`REDIS_DB_PORT`:** The port number of your Redis instance
- **`REDIS_DB_PASSWORD`:** The password for your Redis instance
- **`DEEPGRAM_API_KEY`:** Your Deepgram API key, used for real-time and pre-recorded audio transcription
- **`ADMIN_KEY`:** A temporary key used for authentication during local development (replace with a more secure method in production)
- **`OPENAI_API_KEY`:** Your OpenAI API key, used for accessing OpenAI's language models for chat, memory processing, and more
- **`GITHUB_TOKEN`:** Your GitHub personal access token, used to access GitHub's API for retrieving the latest firmware version
- **`WORKFLOW_API_KEY`:** Your custom API key for securing communication with external workflows or integrations

Make sure to replace the placeholders (`<api-key>`, `<bucket-name>`, etc.) with your actual values.

## Contributing 🤝

We welcome contributions from the open source community! Whether it's improving documentation, adding new features, or reporting bugs, your input is valuable. Check out
our [Contribution Guide](https://docs.omi.me/developer/Contribution/) for more information.

## Support 🆘

If you're stuck, have questions, or just want to chat about Omi:

- **GitHub Issues: 🐛** For bug reports and feature requests
- **Community Forum: 💬** Join our [community forum](https://discord.gg/ZutWMTJnwA) for discussions and questions
- **Documentation: 📚** Check out our [full documentation](https://docs.omi.me/) for in-depth guides

Happy coding! 💻 If you have any questions or need further assistance, don't hesitate to reach out to our community.

