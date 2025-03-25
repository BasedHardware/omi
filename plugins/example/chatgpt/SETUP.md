# Setting Up the OMI ChatGPT Integration

This guide will walk you through the process of setting up the OMI-ChatGPT integration and configuring your OpenAI GPT Actions.

## 1. Setup Environment

First, make sure you have the necessary environment variables set:

1. Copy the `.env.template` file to create a `.env` file:

```bash
cp .env.template .env
```

2. Edit the `.env` file with your credentials:

```
# ChatGPT OAuth Settings
CHATGPT_OAUTH_CLIENT_ID=your_client_id_from_openai
CHATGPT_OAUTH_CLIENT_SECRET=your_client_secret_from_openai
CHATGPT_OAUTH_REDIRECT_URI=https://your-server.com/auth/chatgpt/callback
CHATGPT_AUTH_URL=https://auth.openai.com/oauth/authorize
CHATGPT_TOKEN_URL=https://auth.openai.com/oauth/token

# Redis or other settings as needed
```

## 2. Running the Server Locally for Testing

For local testing, you can run the server directly:

```bash
cd plugins/example/chatgpt
python server.py
```

This will start a FastAPI server on port 8000. Visit `http://localhost:8000/docs` to see the API documentation.

## 3. Creating Your ChatGPT Action in OpenAI

1. Go to OpenAI's developer portal and create a new GPT Action.

2. In the Authentication section, select OAuth as the Authentication Type.

3. Complete the OAuth fields as follows:

   - **Client ID**: Your OpenAI Client ID (from your OpenAI developer account)
   - **Client Secret**: Your OpenAI Client Secret
   - **Authorization URL**: `https://your-server.com/chatgpt/oauth/authorize`
      (Replace with your deployed server URL)
   - **Token URL**: `https://your-server.com/chatgpt/oauth/token`
      (Replace with your deployed server URL)
   - **Scope**: `read:memories` (or whatever scope you defined)
   - **Token Exchange Method**: Keep as "Default (POST request)"

4. In the API Schema section, use the OpenAPI schema from the README.md file.

## 4. Deploying to Production

For production deployment:

1. Deploy your FastAPI application to a server (AWS, Google Cloud, Heroku, etc.)
2. Ensure your server has HTTPS enabled (required for OAuth)
3. Update your `.env` file with production values
4. Update the OAuth URLs in your GPT Action configuration to point to your production server

## 5. Testing the Integration

To test that everything is working:

1. Start a conversation with your custom GPT
2. The first time you try to access OMI data, it will prompt you to connect your OMI account
3. Follow the OAuth flow to authorize the connection
4. The custom GPT should now be able to access your OMI conversations

## 6. Troubleshooting

- **OAuth Error**: Check that your Client ID, Client Secret, and Redirect URI match between your OpenAI settings and your server configuration.
- **Server Not Running**: Ensure your server is running and accessible at the specified URLs.
- **CORS Issues**: If you encounter CORS issues, make sure your server is properly configured to allow requests from OpenAI's domains.
- **Token Expiration**: If access tokens expire, the system should automatically refresh them. If not, check the token refresh implementation.

## 7. Implementing the OAuth Endpoints

To implement the OAuth endpoints expected by OpenAI, you need to:

1. Create an OAuth authorization endpoint at `/chatgpt/oauth/authorize`
2. Create a token endpoint at `/chatgpt/oauth/token`
3. Update your memory_handler.py file with these new endpoints

A sample implementation will be provided in the updated code. 