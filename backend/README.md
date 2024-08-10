# Setup
1. Install the google-cloud-sdk `brew install google-cloud-sdk`
    of if you use nix envdir, it should be installed for you
2. You will need to have your own Google Cloud Project (beyond the scope of this doc…)
    1. You will need to add `Cloud Resource Manager` and `Firebase Management API` in the [Google Cloud API Console](https://console.cloud.google.com/apis/dashboard)
3. Run the following commands one by one
	1. `gcloud auth login`,
	2. `gcloud config set project <project-id>`.
	3. To be on the safe side, run `gcloud auth application-default login --project <project-id>` as well.
	4. This should generate the `application_default_credentials.json` file in the `~/.config/gcloud` directory. This file is read automatically by gcloud in Python, so you don’t have to manually add any env for the service account.
	5. Replace `<project-id>` with your google cloud project id.
4. ~~Make sure you have Firebase setup done locally~~
5. Install Python (use brew if on mac) (or with nix env it will be done for you)
6. Install pip (if it doesn’t exist)
7. Install `git `and `ffmpeg` (use brew if on mac) (again nix env installs this for you)
8. Move to the backend directory (`cd backend`)
	1. Run the command `cat .env.template > .env`
	2. For Redis (you can use [https://upstash.com/](https://upstash.com/ "https://upstash.com/"), sign up and create a free instance)
	3. Add the necessary keys in the env file (openai, deepgram, redis, set ADMIN_KEY to 123)
9.  Run the command `pip install -r requirements.txt`
10. Sign Up on [https://ngrok.com/](https://ngrok.com/ "https://ngrok.com/") and follow the steps to configure it
	1. During the onboarding flow, under the `Static Domain` section, Ngrok should tell you to run a command like `ngrok http --domain=example.ngrok-free.app 80`. In that, replace 80 with 8000. Open a new terminal and run this command
11. Run the command `uvicorn main:app --reload --env-file .env`
12. If you get any error mentioning `no internet connection or something`, then add the following lines in the `utils/stt/vad.py` file after the import statements.
	`import ssl ssl._create_default_https_context = ssl._create_unverified_context`
13. If you get the openai key error, include the following in `utils/llm.py` file after import statements
	`os.environ['OPENAI_API_KEY'] = 'your_key_here'`
14.  If not the above solution, you can try `OPENAI_API_KEY=xyz uvicorn main:app --reload --env-file .env` to fix it as well.
15. Now try running the `uvicorn main:app --reload --env-file .env` command again.
16. Assign the url given by ngrok in the app’s env to `API_BASE_URL`
17. Now your app should be using your local backend (hopefully)

