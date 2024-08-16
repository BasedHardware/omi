import json

data = [
    {
        "text": "Okay. So I start speaking now. So Karen.",
        "speaker": "SPEAKER_0",
        "speaker_id": 0,
        "is_user": True,
        "start": 0.0,
        "end": 7.880000000000109
    },
    {
        "text": "Okay. So I guess if I continue speaking, 1 will represent strippers percent. It means that it's, like, 35 words and all that. As that decent. I don't still like different person. Think that's better than nothing. At least. Isn't it?",
        "speaker": "SPEAKER_0",
        "speaker_id": 0,
        "is_user": True,
        "start": 97.1699000000001,
        "end": 167.87000000000012
    },
    {
        "text": "Okay. So now when I start speaking, it should be considerably better. Alright. So, yeah, Alister speaking. Alright. So messages will change a little bit. Then it says that You are almost there or you are doing great. This is a cute NPP item. I think this is better all. I kinda like logic. It works. Interesting.",
        "speaker": "SPEAKER_0",
        "speaker_id": 0,
        "is_user": True,
        "start": 198.56999999999994,
        "end": 279.21000000000004
    },
    {
        "text": "Great. Quiet.",
        "speaker": "SPEAKER_0",
        "speaker_id": 0,
        "is_user": True,
        "start": 356.24,
        "end": 379.9000000000001
    },
    {
        "text": "It starts running. Hi.",
        "speaker": "SPEAKER_0",
        "speaker_id": 0,
        "is_user": True,
        "start": 419.6298999999999,
        "end": 424.23
    }
]


def execute():
    cleaned = []
    for item in data:
        cleaned.append({
            'speaker_id': item['speaker_id'] + 1 if not item['is_user'] else 0,
            'text': item['text'],
            # 'seconds': [round(item['start'], 2), round(item['end'], 2)]
        })

    print(json.dumps(cleaned, indent=2))


if __name__ == '__main__':
    execute()
