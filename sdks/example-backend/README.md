# Omi Audio Processor

This is a simple backend for the Omi SDK. It is a FastAPI application that listens for WebSocket connections from the Omi SDK and processes the audio data.

## Running the backend

### Using Local Python

1. Install [uv](https://docs.astral.sh/uv/) 
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Run the backend:
```
cd ./sdks/example-backend
uv run python main.py # 
```

### Using Docker

1. Run the backend
```
cd ./sdks/example-backend
docker compose up --build
```

## Exposing the Backend

Expose the backend to the internet using ngrok:
```
ngrok http 8000
```
Copy the ngrok URL and use it in the app.
(You just need an https endpoint, you can use whatever you want)

## Running the App

1. Run the app:
```
cd ./sdks/react-native/example
npm run android
```

2. Click on the "Connect to Backend" button, you should see logs on both the app and backend side.

3. Connect Omi device using bluetooth, check that you get codec and battery level data.

4. Click Start audio listener to send audio data to the backend.

On the backend, audio is saved in both opus and .wav format under example-backend/audio_files