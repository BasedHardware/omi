To fix the issue where the GET /v2/desktop/messages/reconcile endpoint returns raw Firestore dicts, we need to apply the same deserialization guard used in the GET /v2/desktop/messages endpoint. This ensures that any malformed messages are handled correctly.

Here's the updated code:

```python
async def get_desktop_messages_reconcile_page(
    ...,
) -> DesktopMessageReconcilePageResponse:
    try:
        messages = await desktop_message_store.get_messages_reconcile_page(
            cursor=cursor,
        )
        messages = [msg async for msg in Message.deserialize_many_safe(msgs=messages)]
        return DesktopMessageReconcilePageResponse(
            messages=messages,
        )
    except Exception as e:
        logger.error(f"Desktop message reconcile page error: {e}")
        raise
```

This code adds a guard around the messages processing, using `Message.deserialize_many_safe` to handle each message, ensuring that any malformed messages are skipped and logged, preventing 500 errors.