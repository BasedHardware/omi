```python
import json
import uuid
from datetime import datetime

def omi_to_taskwarrior(omi_item):
    task = {}
    task['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, omi_item['id']))
    task['description'] = omi_item['content']
    task['status'] = 'pending' if omi_item['status'] == 'open' else 'completed'
    if omi_item.get('created_at'):
        task['entry'] = omi_item['created_at'].replace(' ', 'T').replace('.000', '000')
    if omi_item.get('updated_at'):
        task['modified'] = omi_item['updated_at'].replace(' ', 'T').replace('.000', '000')
    if omi_item.get('due_at'):
        task['due'] = omi_item['due_at'].replace(' ', 'T').replace('.000', '000')
    if omi_item.get('completed_at'):
        task['end'] = omi_item['completed_at'].replace(' ', 'T').replace('.000', '000')
    if 'tags' in omi_item and len(omi_item['tags']) > 0:
        task['tags'] = ','.join(omi_item['tags'])
    task['uuid'] = task['id']
    task['+'] = 'omi'
    del task['uuid']
    return task

def main():
    import sys
    input = sys.stdin.read().decode('utf-8')
    items = json.loads(input)
    tasks = []
    for item in items:
        tasks.append(omi_to_taskwarrior(item))
    print(json.dumps(tasks, ensure_ascii=False))

if __name__ == '__main__':
    main()
```