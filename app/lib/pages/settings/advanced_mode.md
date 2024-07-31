## Docs Advanced Mode

### Webhooks

Every time a memory is created, a POST request is made to the URL provided with the following JSON
details.

```
{
  'id': 1,
  'createdAt': createdAt.toIso8601String(),
  'transcript': "transcript",
  'structured': {
    'title': "title",
    'overview': "overview",
    'emoji': "emoji",
    'category': "category",
    'actionItems': ["Action item 1", "Action item 2"],
  },
  'pluginsResponse': ["This is a plugin response item"],
  'discarded': false,
}
```

#### Example:

Python FastAPI

```python
from typing import List
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Structured(BaseModel):
    title: str
    overview: str
    emoji: str
    category: str
    actionItems: List[str]


class Memory(BaseModel):
    id: int
    createdAt: str
    transcript: str
    structured: Structured
    pluginsResponse: List[str] = []
    discarded: bool


@app.post("/webhook")
def webhook(memory: Memory):
    print(memory) # process your memory here
    return memory

```

**Things to be implemented soon:**

- [ ] Memory creation has a developer field, of webhook result, if you want to do anything with it,
  it could also be the status code.
- [ ] Include the generated audio file too.

### Custom Transcript Server

To be implemented soon.