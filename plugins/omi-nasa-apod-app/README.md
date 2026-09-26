# Omi NASA Astronomy & Space Exploration App

An integration app for [Omi](https://github.com/BasedHardware/omi) that brings NASA's Astronomy Picture of the Day (APOD) and space mission media archives (JWST, Hubble, Mars Rovers, Apollo) directly to Omi chat tools.

## Features

- **Astronomy Picture of the Day (APOD)**: Daily high-definition astronomy photography and astrophysics explanations from NASA scientists.
- **NASA Mission Media Library**: Search thousands of space photos across historic and active missions.
- **Zero Configuration**: Powered by open NASA APIs.

## Endpoints

- `POST /tools/astronomy_picture_of_the_day`: Get APOD for today, a custom date, or random space pictures.
- `POST /tools/search_nasa_images`: Search NASA's official mission media library.
- `GET /manifest.json`: Omi plugin manifest.
- `GET /.well-known/ai-plugin.json`: OpenAI standard manifest.
- `GET /health`: Service health check.
