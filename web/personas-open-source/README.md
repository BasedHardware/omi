# Personas - Open Source AI Chat Platform With 11 Million Views, 300K Users

Personas is an open-source AI chat platform that allows users to interact with various AI models through a beautiful, modern interface. 
We recently went viral on Twitter with 11 Million Views, 300K+ users. 

Built with Next.js 13, Firebase, and various AI APIs, it offers a seamless experience for users to engage with different AI personalities through Twitter.

## Features

- 🤖 Multiple AI Models Support (OpenRouter API)
- 🔒 User Authentication (Firebase)
- 💬 Real-time Chat Interface
- 📊 Analytics Integration (Mixpanel)
- 🎨 Beautiful Modern UI
- 💾 Chat History Storage

## Prerequisites

Before you begin, ensure you have:
- Node.js 18 or later
- npm or yarn
- Git

## Required API Keys

You'll need to obtain the following API keys and credentials:

1. **Firebase Configuration**
   - Create a project at [Firebase Console](https://console.firebase.google.com/)
   - Enable Authentication (Google Sign-in)
   - Enable Firestore Database
   - Get your Firebase configuration keys

2. **OpenRouter API**
   - Sign up at [OpenRouter](https://openrouter.ai/)
   - Get your API key
   - Access to models like Claude Sonnet and Gemini Flash (100x cheaper than direct API access)

3. **RapidAPI Twitter API**
   - Subscribe to [Twitter API]([https://rapidapi.com/twitterapi/api/twitter-api/](https://rapidapi.com/alexanderxbx/api/twitter-api45/playground/apiendpoint_27b38e0c-f394-4715-a7c2-7a68eec23b99))
   - Get your API key

4. **Mixpanel**
   - Create an account at [Mixpanel](https://mixpanel.com)
   - Get your project token

5. **RapidAPI LinkedIn API**
   - Subscribe to [LinkedIn API](https://rapidapi.com/rockapis-rockapis-default/api/linkedin-api8)
   - Get your API key
   - Access to profile data and posts
   
## Setup Instructions

1. Clone the repository:
   ```bash
   git clone https://github.com/BasedHardware/omi.git
   cd omi/personas-open-source
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Create a `.env.local` file in the root directory with the following variables:
   ```env
   # Firebase Configuration
   NEXT_PUBLIC_FIREBASE_API_KEY=your_firebase_api_key
   NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your_firebase_auth_domain
   NEXT_PUBLIC_FIREBASE_PROJECT_ID=your_firebase_project_id
   NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your_firebase_storage_bucket
   NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=your_firebase_messaging_sender_id
   NEXT_PUBLIC_FIREBASE_APP_ID=your_firebase_app_id
   NEXT_PUBLIC_FIREBASE_VAPID_KEY=your_firebase_vapid_key

   # API Keys
   NEXT_PUBLIC_RAPIDAPI_KEY=your_rapidapi_key
   OPENROUTER_API_KEY=your_openrouter_api_key
   NEXT_PUBLIC_MIXPANEL_TOKEN=your_mixpanel_token
   NEXT_PUBLIC_LINKEDIN_API_HOST=your_rapidapi_linkedin_host
   NEXT_PUBLIC_LINKEDIN_API_KEY=your_rapidapi_linkedin_key
   ```

4. Run the development server:
   ```bash
   npm run dev
   ```

5. Open [http://localhost:3000](http://localhost:3000) in your browser.

## Docker Support

To run using Docker:

1. Build the image:
   ```bash
   docker build -t personas .
   ```

2. Run the container:
   ```bash
   docker run -p 3000:3000 personas
   ```

## Model Selection and Costs

Through OpenRouter, you can access various AI models:

- **Gemini Flash**: Extremely cost-effective, ~$0.0001/1K tokens
- **Claude Sonnet**: High quality with lower cost than direct API access
- Other models available through OpenRouter

## Contributing

We welcome contributions! Please feel free to submit a Pull Request.

## Support

If you encounter any issues or have questions, please open an issue on GitHub.
