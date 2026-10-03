<content>
import os
import subprocess
import tempfile
from pathlib import Path

def test_check_plugin_request_timeouts_pass():
    """Test that the script passes when all requests have timeouts."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a temporary plugin file with requests that have timeouts
        plugin_content = """
import requests

def sync_function():
    requests.get('https://example.com', timeout=5)

async def async_function():
    requests.get('https://example.com', timeout=(3, 30))
"""
        plugin_file = Path(temp_dir) / "test_plugin.py"
        plugin_file.write_text(plugin_content)
        
        # Run the script
        result = subprocess.run(
            ["python", "scripts/check_plugin_request_timeouts.py"],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        
        # Should pass
        assert result.returncode == 0
        assert "All requests calls have timeout parameters." in result.stdout

def test_check_plugin_request_timeouts_fail():
    """Test that the script fails when requests don't have timeouts."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a temporary plugin file with requests without timeouts
        plugin_content = """
import requests

def sync_function():
    requests.get('https://example.com')

async def async_function():
    requests.post('https://example.com', json={'data': 'test'})
"""
        plugin_file = Path(temp_dir) / "test_plugin.py"
        plugin_file.write_text(plugin_content)
        
        # Create a dummy plugins directory
        plugins_dir = Path(temp_dir) / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "test_plugin.py").write_text(plugin_content)
        
        # Run the script
        result = subprocess.run(
            ["python", "scripts/check_plugin_request_timeouts.py"],
            capture_output=True,
            text=True,
            cwd=temp_dir
        )
        
        # Should fail
        assert result.returncode == 1
        assert "Found requests calls without timeout" in result.stdout

def test_check_plugin_request_timeouts_event_loop():
    """Test that the script detects requests on event loop."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a temporary plugin file with async function calling requests
        plugin_content = """
import requests

async def async_function():
    requests.get('https://example.com')  # No timeout - should be detected
"""
        plugin_file = Path(temp_dir) / "test_plugin.py"
        plugin_file.write_text(plugin_content)
        
        # Create a dummy plugins directory
        plugins_dir = Path(temp_dir) / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "test_plugin.py").write_text(plugin_content)
        
        # Run the script
        result = subprocess.run(
            ["python", "scripts/check_plugin_request_timeouts.py"],
            capture_output=True,
            text=True,
            cwd=temp_dir
        )
        
        # Should fail and mention event loop
        assert result.returncode == 1
        assert "Event loop blocking call" in result.stdout
</content>