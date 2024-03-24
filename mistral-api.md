# Using the Mistral API
You can use the Mistral API with your own Authorization bearer key that you can get from: https://console.mistral.ai/api-keys/.
We recommend that you use Mistral Large for Friend as it is the best model available in the .


This provides an overview of authentication, available endpoints with example request bodies, and code examples in Python demonstrating API usage. 


## Authentication
To authenticate with the Mistral API, you need to include an API key in the request headers:

import requests

headers = {
    "Authorization": "Bearer YOUR_API_KEY"
}

```python
response = requests.get("https://api.mistral.co/models", headers=headers)



Create Completion
Generates text based on the provided prompt and model.

Endpoint: POST https://api.mistral.co/completions

```
## Example Request Body:
```python
{
  "model": "mistral-large-latest",
  "prompt": "Summarize the latest conversations that you received into insightful summaries.",
  "max_tokens": 50
}
```
