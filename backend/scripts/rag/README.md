### Setup

1. cd into `scripts/rag`
2. Go to _shared.py and replace the uid variable for yours.
3. Set `os.environ['OPENAI_API_KEY']` manually on _`shared.py`
4. Set your .env file in `../../.env`
5. Run `streamlit run app.py`

#### Troubleshooting

- if you get an error related to this lines, delete memories.json and run it again.
    ```python
    all_embeddings = np.array([item['vector'] for item in data.values()])
    
    topic_embeddings = [openai_embeddings.embed_query(topic) for topic in topics]
    all_embeddings = np.vstack([all_embeddings] + topic_embeddings)
    ```