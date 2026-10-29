import pytest
from unittest.mock import patch, mock_open, MagicMock
from pathlib import Path
from diarizer.batch_pipeline_benchmark import tokens, edit_distance, main


def test_tokens():
    assert tokens("Hello, world!") == ["hello", "world"]
    assert tokens("It's a test.") == ["it's", "a", "test"]
    assert tokens("") == []


def test_edit_distance():
    assert edit_distance(["a", "b", "c"], ["a", "b", "c"]) == 0
    assert edit_distance(["a", "b", "c"], ["a", "x", "c"]) == 1
    assert edit_distance(["a", "b", "c"], ["a", "b"]) == 1
    assert edit_distance(["a", "b"], ["a", "b", "c"]) == 1
    assert edit_distance([], []) == 0
    assert edit_distance(["a"], []) == 1
    assert edit_distance([], ["a"]) == 1


def test_main_raises_runtime_error_without_gpu():
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value.audio = "dummy.wav"
        mock_args.return_value.reference = "dummy.txt"
        mock_args.return_value.vad_json = None
        mock_args.return_value.output = "dummy.json"
        mock_args.return_value.model = "dummy"

        with patch("diarizer.batch_pipeline_benchmark.torch", None):
            with pytest.raises(RuntimeError, match="benchmark requires the GPU runtime with torch and NeMo"):
                main()


def test_main_raises_value_error_without_words():
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value.audio = "dummy.wav"
        mock_args.return_value.reference = "dummy.txt"
        mock_args.return_value.vad_json = None
        mock_args.return_value.output = "dummy.json"
        mock_args.return_value.model = "dummy"

        with patch("diarizer.batch_pipeline_benchmark.torch", MagicMock()):
            with patch("diarizer.batch_pipeline_benchmark.nemo_asr", MagicMock()):
                with patch("pathlib.Path.read_bytes", return_value=b"dummy audio"):
                    with patch("diarizer.batch_pipeline_benchmark.decode_pcm16_wav", return_value=[0] * 16000):
                        with patch("pathlib.Path.read_text", return_value=""):
                            with pytest.raises(ValueError, match="public reference must contain words"):
                                main()


def test_main_runs_successfully():
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value.audio = "dummy.wav"
        mock_args.return_value.reference = "dummy.txt"
        mock_args.return_value.vad_json = None
        mock_args.return_value.output = "dummy.json"
        mock_args.return_value.model = "dummy"

        mock_torch = MagicMock()
        mock_torch.cuda.get_device_name.return_value = "Mock GPU"
        mock_torch.__version__ = "mock_version"
        mock_torch.cuda.max_memory_allocated.return_value = 1024

        mock_nemo_asr = MagicMock()
        mock_model = MagicMock()
        mock_model.cuda.return_value = mock_model
        mock_model.eval.return_value = mock_model
        mock_nemo_asr.models.ASRModel.from_pretrained.return_value = mock_model

        with patch("diarizer.batch_pipeline_benchmark.torch", mock_torch):
            with patch("diarizer.batch_pipeline_benchmark.nemo_asr", mock_nemo_asr):
                with patch("pathlib.Path.read_bytes", side_effect=[b"dummy audio", b"hello world"]):
                    with patch("diarizer.batch_pipeline_benchmark.decode_pcm16_wav", return_value=[0] * 16000):
                        with patch("pathlib.Path.read_text", return_value="hello world"):
                            with patch("diarizer.batch_pipeline_benchmark.pin_parakeet_decoding"):
                                with patch("diarizer.batch_pipeline_benchmark.ParakeetWords") as MockProvider:
                                    mock_provider = MockProvider.return_value
                                    mock_provider.transcribe_batch.return_value = [
                                        [
                                            {"word": "hello", "timestamp": [0.0, 0.5]},
                                            {"word": "world", "timestamp": [0.5, 1.0]},
                                        ]
                                    ]
                                    with patch("pathlib.Path.write_text") as mock_write_text:
                                        with patch("builtins.print") as mock_print:
                                            main()

                                            assert mock_write_text.called
                                            assert mock_print.called
