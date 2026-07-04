from typing import Any, cast

from _shared import *


def get_data(query: str, top_k: int = 1000) -> list[list[Any]]:
    memories = get_memories()
    memories_map = {memory['id']: memory for memory in memories}
    vectors = cast(list[list[Any]], query_vectors(query, uid, k=top_k))

    result: list[list[Any]] = []
    for mid, vector in vectors:
        memory = memories_map.get(mid)
        if not memory:
            continue
        result.append([memory['structured']['title'], vector])
    return result


def visualize() -> None:
    query = ''
    top_k = 1000
    target = 5

    data = get_data(query, top_k=top_k)
    embeddings = cast('np.ndarray', np.array([item[1] for item in data]))

    query_embedding = openai_embeddings.embed_query(query)
    all_embeddings = cast('np.ndarray', np.vstack([embeddings, query_embedding]))

    umap_transform = umap.UMAP(n_components=2, random_state=0, transform_seed=0)
    umap_embeddings = cast(Any, umap_transform.fit_transform(all_embeddings))

    # Separate the query point from the rest
    query_point = umap_embeddings[-1]
    data_points = umap_embeddings[:-1]

    fig = make_subplots(rows=1, cols=1)
    fig_any = cast(Any, fig)

    fig_any.add_trace(get_all_markers(data, data_points, target))
    fig_any.add_trace(get_top_markers(data, data_points, target))
    fig_any.add_trace(get_query_marker(query_point, query))

    generate_html_visualization(fig, file_name='embedding_visualization.html')


if __name__ == '__main__':
    visualize()
