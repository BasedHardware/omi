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
