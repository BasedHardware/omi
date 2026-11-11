from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

RAG_CURRENT_PATH = str(Path(__file__).resolve().parents[2] / 'scripts' / 'rag' / 'current.py')


def _load_visualization_module():
    shared = AutoMockModule('_shared')
    chat = AutoMockModule('models.chat')
    conversation = AutoMockModule('models.conversation')
    umap_module = ModuleType('umap')
    plotly_module = ModuleType('plotly')
    plotly_subplots = ModuleType('plotly.subplots')
    plotly_subplots.make_subplots = MagicMock()
    plotly_module.subplots = plotly_subplots
    umap_module.UMAP = MagicMock()
    with stub_modules(
        {
            '_shared': shared,
            'models.chat': chat,
            'models.conversation': conversation,
            'umap': umap_module,
            'plotly': plotly_module,
            'plotly.subplots': plotly_subplots,
        }
    ):
        return load_module_fresh('rag_current_visualization', RAG_CURRENT_PATH), umap_module


def test_generate_visualization_uses_get_data_without_memories(monkeypatch, tmp_path):
    module, umap_module = _load_visualization_module()
    monkeypatch.chdir(tmp_path)
    module.get_data = MagicMock(
        return_value={
            'memory-1': ['First', [1.0, 0.0], ['topic']],
            'memory-2': ['Second', [0.0, 1.0], []],
        }
    )
    module.get_data2 = MagicMock()
    module.openai_embeddings = SimpleNamespace(embed_query=lambda topic: [0.5, 0.5])
    module.get_markers = MagicMock(return_value=object())
    module.get_query_marker = MagicMock(return_value=object())
    module.generate_html_visualization = MagicMock()
    figure = MagicMock()
    module.make_subplots = MagicMock(return_value=figure)
    umap_instance = MagicMock()
    umap_instance.fit_transform.return_value = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
    umap_module.UMAP.return_value = umap_instance

    module.generate_visualization(['topic'])

    module.get_data.assert_called_once_with(['topic'])
    module.get_data2.assert_not_called()
    assert umap_module.UMAP.call_args.kwargs == {
        'init': 'random',
        'n_neighbors': 2,
        'n_components': 2,
        'random_state': 0,
        'transform_seed': 0,
    }
    assert module.generate_html_visualization.called


def test_generate_visualization_uses_get_data2_with_memories(monkeypatch, tmp_path):
    module, umap_module = _load_visualization_module()
    monkeypatch.chdir(tmp_path)
    memories = [SimpleNamespace(id='memory-1')]
    module.get_data = MagicMock()
    module.get_data2 = MagicMock(
        return_value={
            'memory-1': ['First', [1.0, 0.0], ['topic']],
            'memory-2': ['Second', [0.0, 1.0], []],
        }
    )
    module.openai_embeddings = SimpleNamespace(embed_query=lambda topic: [0.5, 0.5])
    module.get_markers = MagicMock(return_value=object())
    module.get_query_marker = MagicMock(return_value=object())
    module.generate_html_visualization = MagicMock()
    figure = MagicMock()
    module.make_subplots = MagicMock(return_value=figure)
    umap_instance = MagicMock()
    umap_instance.fit_transform.return_value = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
    umap_module.UMAP.return_value = umap_instance

    module.generate_visualization(['topic'], memories)

    module.get_data2.assert_called_once_with(['topic'], memories)
    module.get_data.assert_not_called()
    assert module.generate_html_visualization.called


def test_generate_visualization_keeps_topic_augmented_small_memory_set(monkeypatch, tmp_path):
    module, umap_module = _load_visualization_module()
    monkeypatch.chdir(tmp_path)
    module.get_data = lambda topics: {
        'memory-1': ['First', [1.0, 0.0], ['topic']],
        'memory-2': ['Second', [0.0, 1.0], []],
    }
    module.openai_embeddings = SimpleNamespace(embed_query=lambda topic: [0.5, 0.5])
    module.get_markers = MagicMock(return_value=object())
    module.get_query_marker = MagicMock(return_value=object())
    module.generate_html_visualization = MagicMock()
    module.go = SimpleNamespace(Scatter=MagicMock())
    figure = MagicMock()
    module.make_subplots = MagicMock(return_value=figure)
    umap_instance = MagicMock()
    umap_instance.fit_transform.return_value = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
    umap_module.UMAP.return_value = umap_instance

    module.generate_visualization(['topic'])

    assert umap_instance.fit_transform.call_args.args[0].shape == (3, 2)
    assert module.generate_html_visualization.called


def test_generate_visualization_keeps_all_memory_points_without_topics(monkeypatch, tmp_path):
    module, umap_module = _load_visualization_module()
    monkeypatch.chdir(tmp_path)
    module.get_data = lambda topics: {
        'memory-1': ['First', [1.0, 0.0], []],
        'memory-2': ['Second', [0.0, 1.0], []],
        'memory-3': ['Third', [1.0, 1.0], []],
    }
    module.get_markers = MagicMock(return_value=object())
    module.generate_html_visualization = MagicMock()
    figure = MagicMock()
    module.make_subplots = MagicMock(return_value=figure)
    umap_instance = MagicMock()
    umap_instance.fit_transform.return_value = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
    umap_module.UMAP.return_value = umap_instance

    module.generate_visualization([])

    assert umap_instance.fit_transform.call_args.args[0].shape == (3, 2)
    np.testing.assert_array_equal(module.get_markers.call_args.args[1], np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]]))
    assert umap_module.UMAP.call_args.kwargs['init'] == 'random'
    assert module.generate_html_visualization.called


def test_generate_visualization_skips_empty_data(monkeypatch, tmp_path):
    module, umap_module = _load_visualization_module()
    monkeypatch.chdir(tmp_path)
    module.get_data = lambda topics: {}
    module.generate_html_visualization = MagicMock()

    module.generate_visualization([])

    umap_module.UMAP.assert_not_called()
    module.generate_html_visualization.assert_not_called()


def test_generate_visualization_skips_below_three_samples(monkeypatch, tmp_path):
    module, umap_module = _load_visualization_module()
    monkeypatch.chdir(tmp_path)
    module.get_data = lambda topics: {'memory-1': ['First', [1.0, 0.0], []]}
    module.generate_html_visualization = MagicMock()

    module.generate_visualization([])

    umap_module.UMAP.assert_not_called()
    module.generate_html_visualization.assert_not_called()


def test_generate_visualization_uses_retrieved_memories(monkeypatch, tmp_path):
    module, umap_module = _load_visualization_module()
    monkeypatch.chdir(tmp_path)
    memories = [SimpleNamespace(id='memory-1')]
    module.get_data2 = MagicMock(
        return_value={
            'memory-1': ['First', [1.0, 0.0], ['topic']],
            'memory-2': ['Second', [0.0, 1.0], []],
            'memory-3': ['Third', [1.0, 1.0], []],
        }
    )
    module.get_markers = MagicMock(return_value=object())
    module.generate_html_visualization = MagicMock()
    figure = MagicMock()
    module.make_subplots = MagicMock(return_value=figure)
    umap_instance = MagicMock()
    umap_instance.fit_transform.return_value = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0], [3.0, 3.0]])
    umap_module.UMAP.return_value = umap_instance
    module.openai_embeddings = SimpleNamespace(embed_query=lambda topic: [0.5, 0.5])
    module.get_query_marker = MagicMock(return_value=object())
    module.go = SimpleNamespace(Scatter=MagicMock())

    module.generate_visualization(['topic'], memories=memories)

    module.get_data2.assert_called_once_with(['topic'], memories)
    assert module.generate_html_visualization.called
