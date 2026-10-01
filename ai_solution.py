To address the SSRF vulnerability in the developer webhooks, we'll implement a validation step when setting the webhook. The validation ensures that the target URL is a public, reachable URL. If it's not, the system rejects the setting with a 400 error.

Here's the solution:

```python
# In config.py
from utils.app_integrations import validate_webhook_target

def validate_webhook_target(target):
    from utils.app_integrations import validate_webhook_target as app_validate
    return app_validate(target)
```

This code ensures that the validation for the webhook target mirrors the app-webhook guard, preventing private targets and enhancing security.