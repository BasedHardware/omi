import json
import os
# noinspection PyUnresolvedReferences
from typing import List

# noinspection PyUnresolvedReferences
import numpy as np
# noinspection PyUnresolvedReferences
import plotly.graph_objects as go
# noinspection PyUnresolvedReferences
import umap
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone
# noinspection PyUnresolvedReferences
from plotly.subplots import make_subplots

# noinspection PyUnresolvedReferences
from models.memory import Memory

load_dotenv('../../.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

if os.getenv('PINECONE_API_KEY') is not None:
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY', ''))
    index = pc.Index(os.getenv('PINECONE_INDEX_NAME', ''))
else:
    index = None

import database.memories as memories_db
# noinspection PyUnresolvedReferences
import database.facts as facts_d

uid = 'viUv7GtdoHXbK1UBCDlPuTDuPgJ2'

openai_embeddings = OpenAIEmbeddings(model="text-embedding-3-large")


def query_vectors(query: str, uid: str, k: int = 1000) -> List[str]:
    xq = openai_embeddings.embed_query(query)
    xc = index.query(vector=xq, top_k=k, filter={'uid': uid}, namespace="ns1", include_values=True)
    data = []
    for item in xc['matches']:
        data.append([item['id'].replace(f'{uid}-', ''), item['values']])
    print('Found:', len(data), 'vectors')
    return data


def get_memories(ignore_cached: bool = False):
    if not os.path.exists('memories.json') or ignore_cached:
        memories = memories_db.get_memories(uid, limit=1000)
        if ignore_cached:
            return memories

        with open('memories.json', 'w') as f:
            f.write(json.dumps(memories, indent=4, default=str))

    with open('memories.json', 'r') as f:
        return json.loads(f.read())


def get_all_markers(data, data_points, target):
    return go.Scatter(
        x=data_points[target:, 0],
        y=data_points[target:, 1],
        mode='markers',
        marker=dict(size=8, opacity=0.5, color='blue'),
        text=[f"{item[0]}" for item in data[5:]],
        hoverinfo='text',
        name='Other Memories'
    )


def get_top_markers(data, data_points, target):
    return go.Scatter(
        x=data_points[:target, 0],
        y=data_points[:target, 1],
        mode='markers',
        marker=dict(size=10, opacity=0.8, color='green'),
        text=[f"Top {i + 1}: {item[0]}" for i, item in enumerate(data[:5])],
        hoverinfo='text',
        name='Top Matches'
    )


def get_query_marker(query_point, query):
    return go.Scatter(
        x=[query_point[0]],
        y=[query_point[1]],
        mode='markers',
        marker=dict(
            symbol='x',
            size=12,
            color='red',
            line=dict(width=2)
        ),
        text=[query],
        hoverinfo='text',
        name='Query'
    )


def generate_html_visualization(fig, file_name: str = 'embedding_visualization.html'):
    fig.update_layout(
        title=f'Embedding Visualization',
        xaxis_title='UMAP Dimension 1',
        yaxis_title='UMAP Dimension 2',
        width=800,
        height=600,
        showlegend=True
    )

    # Generate HTML
    html_content = f'''
        <html>
            <head>
                <title>Embedding Visualization</title>
                <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
            </head>
            <body>
                <div id="plotDiv"></div>
                <script>
                    var plotlyData = {fig.to_json()};
                    Plotly.newPlot('plotDiv', plotlyData.data, plotlyData.layout);
                </script>
            </body>
        </html>
        '''

    with open(file_name, 'w') as f:
        f.write(html_content)

    print(f"HTML file '{file_name}' has been generated.")
