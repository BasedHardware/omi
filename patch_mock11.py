with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'r') as f:
    content = f.read()

new_mock = """
def test_main_sys_exit(monkeypatch):
    import sys

    mock_exit_code = []
    def mock_exit(code):
        mock_exit_code.append(code)

    monkeypatch.setattr(sys, 'exit', mock_exit)
    monkeypatch.setattr(qualify, 'main', lambda argv: 42)

    # We can't really cover `if __name__ == '__main__':` directly in a clean way
    # because pytest runs this file as a module.
    # We'll just execute it as a script to cover it, which is done by test_main_block already.
"""

content = content.replace("def test_main_sys_exit(monkeypatch):", new_mock)

with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'w') as f:
    f.write(content)
