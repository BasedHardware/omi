```python
def search_files_tool(
    cfg,
    question: str,
    file_ids: str | list[str],
    start_seconds: str | float,
    end_seconds: str | float,
) -> dict:
    """
    Enhanced search_files_tool with input validation and resilience.
    """
    try:
        # Validate and extract user_id with configurable fallback
        if isinstance(cfg, dict):
            user_id = cfg.get('configurable', {}).get('user_id')
            if user_id is None:
                user_id = cfg.get('user_id')
        else:
            user_id = None

        # Validate question
        if not isinstance(question, str):
            raise ValueError("Question must be a string.")
        question = question.strip()
        if not question:
            return {"files": [], "error": "Question is empty or whitespace."}

        # Validate file_ids
        if isinstance(file_ids, str):
            file_ids = file_ids.split(',') if file_ids else []
        elif not isinstance(file_ids, (list, tuple)):
            raise ValueError("file_ids must be a string, list, or tuple.")

        # Validate start and end seconds
        try:
            start_seconds = float(start_seconds) if start_seconds else 0.0
            start_seconds = max(start_seconds, 0.0)
            end_seconds = float(end_seconds) if end_seconds else 0.0
            end_seconds = max(end_seconds, 0.0)
        except (ValueError, TypeError):
            return {"files": [], "error": "start_seconds or end_seconds are invalid."}

        # Process with validated inputs
        return FileChatTool.process_chat_with_file(
            cfg,
            user_id=user_id,
            question=question,
            file_ids=file_ids,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )

    except Exception as e:
        return {
            "files": [],
            "error": f"Input validation error: {str(e)}"
        }
```