```python
def get_slack_error(e):
    return {"error": f"Internal server error: {str(e)}"}

# Auth endpoint
@slack_app.post("/auth")
async def slack_auth(request: Request, data: dict = Body(...)) -> dict:
    try:
        result = await slack_auth_logic(request, data)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Slack auth error: {str(e)}")
        return get_slack_error(e)

# Update channel endpoint
@slack_app.post("/update-channel")
async def slack_update_channel(request: Request, data: dict = Body(...)) -> dict:
    try:
        await slack_update_channel_logic(request, data)
        return {"success": True}
    except Exception as e:
        logger.error(f"Slack update channel error: {str(e)}")
        return {"success": False, "error": get_slack_error(e)}

# Refresh channels endpoint
@slack_app.post("/refresh-channels")
async def slack_refresh_channels(request: Request) -> dict:
    try:
        await slack_refresh_channels_logic(request)
        return {"success": True}
    except Exception as e:
        logger.error(f"Slack refresh channels error: {str(e)}")
        return {"success": False, "error": get_slack_error(e)}

# Logout endpoint
@slack_app.post("/logout")
async def slack_logout(request: Request) -> dict:
    try:
        await slack_logout_logic(request)
        return {"success": True}
    except Exception as e:
        logger.error(f"Slack logout error: {str(e)}")
        return {"success": False, "error": get_slack_error(e)}

# Webhook endpoint
@slack_app.post("/webhook")
async def slack_webhook(request: Request, data: dict = Body(...)) -> dict:
    try:
        await slack_webhook_logic(request, data)
        return {"success": True}
    except Exception as e:
        logger.error(f"Slack webhook error: {str(e)}")
        return get_slack_error(e)

# Send message endpoint
@slack_app.post("/api/send_message")
async def slack_send_message(request: Request, data: dict = Body(...)) -> dict:
    try:
        await slack_send_message_logic(request, data)
        return {"success": True}
    except Exception as e:
        logger.error(f"Slack send message error: {str(e)}")
        return {"error": get_slack_error(e)}

# Search messages endpoint
@slack_app.post("/api/search_messages")
async def slack_search_messages(request: Request, data: dict = Body(...)) -> dict:
    try:
        result = await slack_search_messages_logic(request, data)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Slack search messages error: {str(e)}")
        return {"error": get_slack_error(e)}

# Search channels endpoint
@slack_app.post("/api/search_channels")
async def slack_search_channels(request: Request, data: dict = Body(...)) -> dict:
    try:
        result = await slack_search_channels_logic(request, data)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Slack search channels error: {str(e)}")
        return {"error": get_slack_error(e)}
```