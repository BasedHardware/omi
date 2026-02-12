"""
Claude Code-like agentic implementation using Anthropic API with tools.
Implements exploration and iteration like Claude Code CLI.
"""
import os
import subprocess
import tempfile
import logging
from typing import Optional, Dict, Any, List
from anthropic import Anthropic

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_agentic_claude_on_repo(
    repo_url: str,
    feature_description: str,
    branch_name: str,
    github_token: str,
    anthropic_key: str,
    max_iterations: int = 15
) -> Dict[str, Any]:
    """
    Clone repo, run agentic Claude to implement feature, return changes.
    Claude can explore files and iterate like Claude Code CLI.

    Args:
        repo_url: GitHub repo URL
        feature_description: What to implement
        branch_name: Branch name for changes
        github_token: GitHub access token
        anthropic_key: Anthropic API key
        max_iterations: Max tool use iterations

    Returns:
        Dict with success status and branch info
    """
    try:
        # Create temp directory for repo
        with tempfile.TemporaryDirectory() as tmpdir:
            logger.info(f"Cloning {repo_url} to {tmpdir}")

            # Clone repo with auth
            auth_url = repo_url.replace('https://', f'https://{github_token}@')
            clone_result = subprocess.run(
                ['git', 'clone', auth_url, tmpdir],
                capture_output=True,
                text=True,
                timeout=60
            )

            if clone_result.returncode != 0:
                return {
                    'success': False,
                    'message': f'Failed to clone repo: {clone_result.stderr}'
                }

            logger.info(f"Cloned successfully, creating branch {branch_name}")

            # Create new branch
            subprocess.run(
                ['git', 'checkout', '-b', branch_name],
                cwd=tmpdir,
                check=True
            )

            # Get default branch
            default_branch_result = subprocess.run(
                ['git', 'remote', 'show', 'origin'],
                cwd=tmpdir,
                capture_output=True,
                text=True
            )

            default_branch = 'main'
            for line in default_branch_result.stdout.split('\n'):
                if 'HEAD branch:' in line:
                    default_branch = line.split(':')[1].strip()
                    break

            # Run agentic Claude with file access
            client = Anthropic(api_key=anthropic_key)

            # Define tools Claude can use
            tools = [
                {
                    "name": "read_file",
                    "description": "Read contents of a file in the repository. Use this to explore existing code.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to file relative to repo root"
                            }
                        },
                        "required": ["file_path"]
                    }
                },
                {
                    "name": "list_files",
                    "description": "List files in a directory. Use this to explore repo structure.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "dir_path": {
                                "type": "string",
                                "description": "Directory path relative to repo root (use '.' for root)"
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "List files recursively"
                            }
                        },
                        "required": ["dir_path"]
                    }
                },
                {
                    "name": "write_file",
                    "description": "Write or update a file. Use this to implement the feature.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to file relative to repo root"
                            },
                            "content": {
                                "type": "string",
                                "description": "Full file contents to write"
                            }
                        },
                        "required": ["file_path", "content"]
                    }
                },
                {
                    "name": "bash",
                    "description": "Run a bash command in the repo directory. Use for git status, grep, find, etc.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Bash command to run"
                            }
                        },
                        "required": ["command"]
                    }
                }
            ]

            # Initial prompt
            messages = [{
                "role": "user",
                "content": f"""You are implementing a feature in a cloned GitHub repository.

**Feature to implement:** {feature_description}

**Your task:**
1. First, explore the repository structure to understand the codebase
2. Find existing relevant files (use list_files, read_file, bash grep/find)
3. Understand the existing patterns and architecture
4. Implement the feature by modifying existing files (prefer editing over creating new files)
5. When done, tell me "IMPLEMENTATION_COMPLETE"

**Available tools:**
- read_file: Read any file to understand code
- list_files: List directory contents
- write_file: Write/update files
- bash: Run commands (git status, grep, find, etc.)

**Guidelines:**
- Explore first, code second
- Modify existing files rather than creating new ones
- Follow existing code patterns
- Be thorough in understanding before implementing

Start by exploring the repository structure."""
            }]

            iteration = 0
            while iteration < max_iterations:
                iteration += 1
                logger.info(f"Iteration {iteration}/{max_iterations}")

                # Call Claude with tools
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=8000,
                    tools=tools,
                    messages=messages
                )

                logger.info(f"Response stop_reason: {response.stop_reason}")

                # Check if Claude is done
                if response.stop_reason == "end_turn":
                    # Check if Claude said implementation is complete
                    for block in response.content:
                        if hasattr(block, 'text') and 'IMPLEMENTATION_COMPLETE' in block.text:
                            logger.info("Claude finished implementation")
                            break
                    break

                # Process tool calls
                if response.stop_reason == "tool_use":
                    # Add Claude's response to messages
                    messages.append({
                        "role": "assistant",
                        "content": response.content
                    })

                    # Execute tools and collect results
                    tool_results = []

                    for block in response.content:
                        if block.type == "tool_use":
                            tool_name = block.name
                            tool_input = block.input
                            tool_id = block.id

                            logger.info(f"Tool: {tool_name}, Input: {tool_input}")

                            # Execute tool
                            result = execute_tool(tool_name, tool_input, tmpdir)

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": result
                            })

                    # Add tool results to messages
                    messages.append({
                        "role": "user",
                        "content": tool_results
                    })

                else:
                    # Unexpected stop reason
                    break

            # Stage and commit all changes
            logger.info("Staging changes...")
            subprocess.run(['git', 'add', '-A'], cwd=tmpdir, check=True)

            # Check if there are changes
            status_result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=tmpdir,
                capture_output=True,
                text=True
            )

            if not status_result.stdout.strip():
                return {
                    'success': False,
                    'message': 'No changes were made by Claude'
                }

            # Commit
            subprocess.run(
                ['git', 'commit', '-m', f'feat: {feature_description}\n\nGenerated by Claude Code (agentic) via Omi'],
                cwd=tmpdir,
                check=True
            )

            # Push
            logger.info(f"Pushing branch {branch_name}...")
            push_result = subprocess.run(
                ['git', 'push', 'origin', branch_name],
                cwd=tmpdir,
                capture_output=True,
                text=True
            )

            if push_result.returncode != 0:
                return {
                    'success': False,
                    'message': f'Failed to push: {push_result.stderr}'
                }

            return {
                'success': True,
                'branch': branch_name,
                'default_branch': default_branch,
                'message': f'Implemented and pushed to {branch_name}'
            }

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {
            'success': False,
            'message': str(e)
        }


def execute_tool(tool_name: str, tool_input: Dict, repo_dir: str) -> str:
    """Execute a tool and return the result."""
    try:
        if tool_name == "read_file":
            file_path = os.path.join(repo_dir, tool_input['file_path'])
            with open(file_path, 'r') as f:
                content = f.read()
            return content[:10000]  # Limit to 10k chars

        elif tool_name == "list_files":
            dir_path = os.path.join(repo_dir, tool_input['dir_path'])
            recursive = tool_input.get('recursive', False)

            if recursive:
                result = subprocess.run(
                    ['find', '.', '-type', 'f'],
                    cwd=dir_path,
                    capture_output=True,
                    text=True
                )
            else:
                result = subprocess.run(
                    ['ls', '-la'],
                    cwd=dir_path,
                    capture_output=True,
                    text=True
                )

            return result.stdout[:5000]  # Limit output

        elif tool_name == "write_file":
            file_path = os.path.join(repo_dir, tool_input['file_path'])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w') as f:
                f.write(tool_input['content'])

            return f"Successfully wrote {len(tool_input['content'])} chars to {tool_input['file_path']}"

        elif tool_name == "bash":
            result = subprocess.run(
                tool_input['command'],
                shell=True,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30
            )

            output = result.stdout + result.stderr
            return output[:5000]  # Limit output

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Error executing {tool_name}: {str(e)}"
