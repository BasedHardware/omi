import os
import uuid
from datetime import datetime, timezone
from typing import Any, List, cast

import numpy as np
import umap
from plotly.subplots import make_subplots  # type: ignore[reportUnknownVariableType]  # plotly partially typed

from _shared import *
from models.chat import Message, MessageSender, MessageType
from models.conversation import Conversation


def _get_mesage(text: str, sender: str) -> Message:
    return Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender=MessageSender(sender),
        type=MessageType.text,
    )


conversation = [
    _get_mesage('Hi', 'human'),
    _get_mesage('Hi, how can I help you today?', 'ai'),
    _get_mesage('Have I learned about business, and entreprenurship?', 'human'),
]


def get_data(topics: List[str], top_k: int = 1000) -> dict[str, List[Any]]:
    memories = get_memories()
    memories = {memory['id']: memory for memory in memories}
    all_vectors = query_vectors('', uid, k=top_k)
    all_vectors_dict: dict[str, dict[str, Any]] = {mid: {'vector': vector, 'topics': []} for mid, vector in all_vectors}
    for topic in topics:
        vectors = query_vectors(topic, uid, k=5)
        for mid, _vector in vectors:
            if mid in all_vectors_dict:
                all_vectors_dict[mid]['topics'].append(topic)

    result: dict[str, List[Any]] = {}
    for mid, data in all_vectors_dict.items():
        memory = memories.get(mid)
        if not memory:
            continue
        result[mid] = [
            memory['structured']['title'],
            data['vector'],
            data['topics'],
        ]

    return result


def get_markers(
    data: dict[str, List[Any]],
    data_points: Any,
    color: str,
    name: str,
    show_top: int | None = None,
) -> Any:
    if show_top:
        data_items = list(data.items())[:show_top]
        data_points = data_points[:show_top]
    else:
        data_items = list(data.items())

    return go.Scatter(
        x=data_points[:, 0],
        y=data_points[:, 1],
        mode='markers',
        marker=dict(size=8, opacity=0.7, color=color),
        text=[f"Title: {item[1][0]}<br>Topics: {', '.join(item[1][2])}" for item in data_items],
        hoverinfo='text',
        name=name,
    )


def get_data2(topics: List[str], retrieved_memories: List[Conversation]) -> dict[str, List[Any]]:
    # print('get_data2', len(topics), topics)
    # print('retrieved_memories', len(retrieved_memories))
    memories = get_memories()
    memories = {memory['id']: memory for memory in memories}
    all_vectors = query_vectors('', uid, k=1000)
    all_vectors_dict: dict[str, dict[str, Any]] = {mid: {'vector': vector, 'topics': []} for mid, vector in all_vectors}

    result: dict[str, List[Any]] = {}
    retrieved_memories_id = {memory.id for memory in retrieved_memories}
    for mid, data in all_vectors_dict.items():
        memory = memories.get(mid)
        if not memory:
            continue
        result[mid] = [
            memory['structured']['title'],
            data['vector'],
            [] if memory['id'] not in retrieved_memories_id else topics,
        ]

    return result


def generate_visualization(
    topics: List[str],
    memories: List[Conversation] | None = None,
    file_path: str = 'embedding_visualization_multi_topic.html',
) -> None:
    # context: Tuple = determine_requires_context(conversation)
    # if not context or not context[0]:
    #     print('No context is needed')
    #     return
    # topics = context[0]
    # topics = ['Business', 'Entrepreneurship', 'Failures']
    print('topics', topics)
    os.makedirs('visualizations/', exist_ok=True)
    file_path = os.path.join('visualizations/', file_path)

    if memories is not None:
        data = get_data2(topics, memories)
    else:
        data = get_data(topics)
    # print('data', len(data))

    embedding_values = [item[1] for item in data.values()]
    if not embedding_values:
        return

    all_embeddings = cast(Any, np.array(embedding_values))
    if all_embeddings.ndim != 2:
        return

    topic_points: Any = []
    if topics:
        topic_embeddings = [openai_embeddings.embed_query(topic) for topic in topics]
        all_embeddings = cast(Any, np.vstack([all_embeddings] + topic_embeddings))

    if all_embeddings.shape[0] < 3:
        return

    umap_transform = cast(
        Any,
        umap.UMAP(
            init='random' if all_embeddings.shape[0] == 3 else 'spectral',
            n_neighbors=min(15, all_embeddings.shape[0] - 1),
            n_components=2,
            random_state=0,
            transform_seed=0,
        ),
    )
    umap_embeddings = umap_transform.fit_transform(all_embeddings)

    if topics:
        data_points = umap_embeddings[: -len(topics)]
        topic_points = umap_embeddings[-len(topics) :]
    else:
        data_points = umap_embeddings

    fig: Any = make_subplots(rows=1, cols=1)

    colors = ['blue', 'green', 'orange', 'purple', 'cyan', 'magenta']

    # Add all vectors
    fig.add_trace(get_markers(data, data_points, 'gray', 'All Vectors'))

    # Add vectors for each topic
    for i, topic in enumerate(topics):
        color = colors[i % len(colors)]
        topic_data = {mid: item for mid, item in data.items() if topic in item[2]}
        topic_data_points = cast(
            Any, np.array([data_points[list(data.keys()).index(mid)] for mid in topic_data.keys()])
        )

        fig.add_trace(get_markers(topic_data, topic_data_points, color, f'Top 5 - {topic}'))
        fig.add_trace(get_query_marker(topic_points[i], topic))

    fig.update_layout(
        title='Embedding Visualization for Multiple Topics',
        xaxis_title='UMAP Dimension 1',
        yaxis_title='UMAP Dimension 2',
        width=800,
        height=600,
        showlegend=True,
        hovermode='closest',
    )

    generate_html_visualization(fig, file_name=file_path)


if __name__ == '__main__':
    generate_visualization([])
