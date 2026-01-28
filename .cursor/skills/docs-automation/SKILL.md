---
name: docs-automation
description: "Automate documentation updates when API endpoints, functions, or architecture change. Detects code changes that require doc updates, generates API reference from FastAPI routers, updates architecture diagrams, and syncs between internal and external docs."
---

# Documentation Automation Skill

Automate documentation updates to keep docs in sync with code changes.

## When to Use

Use this skill when:
- API endpoints are added, modified, or removed
- Functions or classes are significantly changed
- Architecture changes occur
- New features are implemented
- Breaking changes are introduced

## Capabilities

### 1. Detect Code Changes

Automatically detect changes that require documentation updates:
- Monitor `backend/routers/**/*.py` for API endpoint changes
- Monitor `backend/utils/**/*.py` for function/class changes
- Monitor architecture files for structural changes
- Use git diff to identify what changed

### 2. Generate API Reference

Automatically generate API reference documentation:
- Extract endpoint information from FastAPI routers
- Parse route decorators (`@router.get`, `@router.post`, etc.)
- Extract function docstrings for endpoint descriptions
- Parse request/response models from type hints
- Extract query parameters, path parameters, and request bodies
- Generate MDX documentation files with examples
- Update `.cursor/API_REFERENCE.md`
- Update `docs/api-reference/endpoint/*.mdx`
- Update `docs/doc/developer/api/*.mdx`

**Process**:
1. Scan `backend/routers/**/*.py` for route decorators
2. Extract endpoint metadata:
   - HTTP method (GET, POST, etc.)
   - Path pattern
   - Function name and docstring
   - Parameters (path, query, body)
   - Response model
   - Tags
3. Parse FastAPI models for request/response schemas
4. Generate MDX file with:
   - Endpoint description from docstring
   - Request/response examples
   - Parameter documentation
   - Error codes
5. Update API reference index

**Example**:
```python
@router.post("/v1/conversations", response_model=CreateConversationResponse, tags=['conversations'])
def process_in_progress_conversation(
    request: ProcessConversationRequest = None, 
    uid: str = Depends(auth.get_current_user_uid)
):
    """
    Process an in-progress conversation after recording is complete.
    ...
    """
```

Generates:
```mdx
### Process In-Progress Conversation

`POST /v1/conversations`

Process an in-progress conversation after recording is complete.

**Request Body**: ProcessConversationRequest (optional)

**Response**: CreateConversationResponse
```

### 3. Update Architecture Diagrams

Generate and update architecture diagrams:
- Analyze code structure to generate Mermaid diagrams
- Update `.cursor/ARCHITECTURE.md` with new components
- Update `.cursor/DATA_FLOW.md` if data flows change
- Update component documentation files

### 4. Sync Documentation

Keep documentation synchronized:
- Sync between `.cursor/` internal docs and `docs/` external docs
- Ensure consistency across documentation locations
- Update cross-references and links
- Validate documentation structure

## Workflow

1. **Detect Changes**: Analyze git diff or file changes
2. **Identify Impact**: Determine which documentation needs updating
3. **Generate Updates**: Create or update relevant documentation files
4. **Validate**: Check documentation for completeness and accuracy
5. **Sync**: Ensure all documentation locations are in sync

## Usage Examples

### Automatic API Documentation

When a new endpoint is added to `backend/routers/conversations.py`:
1. Detect the new route decorator using AST parsing
2. Extract endpoint details:
   - Method from decorator (`@router.post` → POST)
   - Path from decorator argument
   - Function docstring for description
   - Parameters from function signature
   - Response model from `response_model` argument
3. Parse request/response models:
   - Extract field names and types
   - Generate JSON examples
   - Document required vs optional fields
4. Generate MDX documentation file:
   - Create `docs/api-reference/endpoint/{endpoint_name}.mdx`
   - Include description, parameters, examples
   - Add to API reference index
5. Update `.cursor/API_REFERENCE.md` with new endpoint
6. Validate documentation format and links

### Parsing FastAPI Routers

**Implementation approach**:
```python
import ast
from typing import List, Dict

def parse_fastapi_router(file_path: str) -> List[Dict]:
    """Parse FastAPI router file and extract endpoint information."""
    with open(file_path) as f:
        tree = ast.parse(f.read())
    
    endpoints = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Check for route decorators
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    # Extract @router.post("/path", ...)
                    method = get_decorator_method(decorator)
                    path = get_decorator_path(decorator)
                    response_model = get_response_model(decorator)
                    
                    endpoints.append({
                        'method': method,
                        'path': path,
                        'function_name': node.name,
                        'docstring': ast.get_docstring(node),
                        'parameters': parse_parameters(node),
                        'response_model': response_model,
                    })
    return endpoints
```

### Architecture Update

When a new module is added:
1. Detect new module structure
2. Update architecture documentation
3. Generate/update Mermaid diagrams
4. Update component references

## Related Resources

### Rules
- `.cursor/rules/documentation-standards.mdc` - Documentation standards
- `.cursor/rules/auto-documentation.mdc` - Auto-documentation rules
- `.cursor/rules/backend-api-patterns.mdc` - API patterns

### Subagents
- `.cursor/agents/docs-generator.md` - Documentation generation subagent

### Commands
- `/auto-docs` - Trigger automatic documentation update
- `/update-api-docs` - Update API reference documentation from FastAPI routers
- `/docs` - Generate or update documentation

## Implementation Notes

### FastAPI Router Parsing

To auto-generate API docs:

1. **Parse Router Files**: Use AST to parse Python files and extract route decorators
2. **Extract Metadata**: Get method, path, parameters, response models from decorators
3. **Parse Docstrings**: Extract endpoint descriptions from function docstrings
4. **Generate Examples**: Create request/response examples from Pydantic models
5. **Generate MDX**: Create MDX files following documentation standards
6. **Update Index**: Add new endpoints to API reference index

### Tools and Libraries

- **AST**: Python's Abstract Syntax Tree for parsing Python code
- **Pydantic**: Extract model schemas for request/response examples
- **FastAPI**: Use FastAPI's OpenAPI schema generation capabilities
- **MDX**: Generate MDX files with proper frontmatter and formatting

### Automation Triggers

- **Git Hooks**: Run on commit if router files changed
- **CI/CD**: Run in CI pipeline to validate docs are up to date
- **Manual**: Use `/update-api-docs` command when needed
