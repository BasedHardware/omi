# Under Construction
- Over the next couple days I will be refactoring so code will move around. I have also done very little for the UI. My goal is to get the functionality working first. If someone wants to work on something the UI would be the place to start for now.

## Overview
This document provides a preliminary overview of the mobile application development process. Detailed instructions and further documentation will be provided at a later stage.

## Requirements
- **MongoDB**: Ensure MongoDB is set up and accessible.
- **Google Cloud Accounts**: Required for various cloud services.
- **API Keys**: Obtain necessary API keys from Deepgram and OpenAI.

## Environment Setup

### Dependencies
- From the friend directory, run `npm install` to install all dependencies

- `python -m venv venv` to create a virtual environment
- `source venv/bin/activate` to activate the virtual environment
- `pip install -r requirements.txt` to install all Python dependencies

### Server Environment Variables
- `OPENAI_API_KEY`: (Specify your OpenAI API key here)
- `LOCAL_DEV`: 'True'
- `MONGO_URI`: (Specify your MongoDB URI here)

### Client Environment Variables
- `BACKEND_URL`: "Your local IP address"
- `DEEPGRAM_API_KEY`: (Specify your Deepgram API key here)

## Running the Application

### Starting the Server
Navigate to the `server/functions` directory and run:

```./launchLocally.sh```


### Starting the Client
For iOS:
```npm run ios```

For Android (untested):

```npm run android```



## Streaming Flow
1. **Start**: Press 'Record' to start streaming.
2. **Silence Detection**: If 30 seconds of silence is detected, the previous stream ends and a new moment is created.
3. **Token Handling**: During a long stream, if the token counter exceeds 500 tokens, that chunk is sent off for extraction. A new moment and snapshot are created in the database and UI.
4. **Extraction and Embedding**: Every 500 tokens are captured, extracted, and embedded.
5. **Updates**: The AI compares the summary, title, and action items from the next snapshot to the previous one, updating the UI with a 'rolling extraction'.
6. **Storage**: Each chunk is stored individually, but the Moment is updated with the most recent snapshot.

## Chat Functionality
The chat functionality is operational. Integration with RAG is planned and will be completed shortly.


## BLE Device

When tha app starts the device detection happens automatically. Your friend should be waiting for you when you get to settings. If no device is connected the app will use the phone's microphone.

## Future Updates
Further details and instructions will be provided as development progresses.