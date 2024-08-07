# Uber Plugin

This plugin allows you to order an Uber ride by mentioning the phrase "get me an Uber from A to B" where A is the start location and B is the end location.

## Setup

1. Obtain your Uber API key by following the instructions on the [Uber Developer Portal](https://developer.uber.com/).
2. Add the `UBER_API_KEY` to your `.env` file in the `plugins/example` directory.

```dotenv
UBER_API_KEY=your_uber_api_key_here
```

## Usage

1. Ensure the plugin is included in the FastAPI application by importing and including the router in `plugins/example/main.py`.

```python
from order_uber import router as order_uber_router

app.include_router(order_uber_router)
```

2. Use the endpoint `/order-uber` to order an Uber ride by sending a POST request with the start and end locations.

```json
{
  "start_location": "A",
  "end_location": "B"
}
```

The plugin will respond with a message indicating the status of the Uber order.