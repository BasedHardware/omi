import requests

from models import Memory


def store_memoy_in_db(notion_api_key: str, database_id: str, memory: Memory):
    # TODO: validate table exists and has correct fields
    data = {
        "parent": {"database_id": database_id},
        "icon": {
            "type": "emoji",
            "emoji": f"{memory.structured.emoji.encode('latin1').decode('utf-8')}"
        },
        "properties": {
            "Title": {"title": [{"text": {"content": f'{memory.structured.title}'}}]},
            "Category": {"select": {"name": memory.structured.category}},
            "Overview": {"rich_text": [{"text": {"content": memory.structured.overview}}]},
            "Speakers": {'number': len(set(map(lambda x: x.speaker, memory.transcriptSegments)))},
            "Duration (seconds)": {'number': (
                        memory.finishedAt - memory.startedAt).total_seconds() if memory.finishedAt is not None else 0},
        }
    }
    resp = requests.post('https://api.notion.com/v1/pages', json=data, headers={
        'Authorization': f'Bearer {notion_api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Notion-Version': '2022-06-28'
    })
    print(resp.json())
    # TODO: after, write inside the page the transcript and everything else.
    return resp.status_code == 200
