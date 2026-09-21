```python
try:
    # some code that may raise an exception
except Exception as e:
    logger.exception(str(e))
    return ChatToolResponse(error="An error occurred while processing your request. Please try again.")
```