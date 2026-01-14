import importlib
import sys
import types


def _ensure_package(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
    return module


def _ensure_module(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


def install_mcp_stubs() -> list[str]:
    created = []

    _ensure_package("database")
    _ensure_package("utils")
    _ensure_package("utils.llm")

    if "database.action_items" not in sys.modules:
        created.append("database.action_items")
    action_items = _ensure_module("database.action_items")

    def _not_implemented(*_args, **_kwargs):
        raise NotImplementedError("Stubbed module; override in test with monkeypatch.")

    action_items.get_action_item = _not_implemented
    action_items.get_action_items = _not_implemented
    action_items.create_action_item = _not_implemented
    action_items.update_action_item = _not_implemented
    action_items.delete_action_item = _not_implemented

    if "database.memories" not in sys.modules:
        created.append("database.memories")
    _ensure_module("database.memories")
    if "database.conversations" not in sys.modules:
        created.append("database.conversations")
    _ensure_module("database.conversations")
    if "database.users" not in sys.modules:
        created.append("database.users")
    _ensure_module("database.users")
    if "database.mcp_api_key" not in sys.modules:
        created.append("database.mcp_api_key")
    _ensure_module("database.mcp_api_key")
    if "database._client" not in sys.modules:
        created.append("database._client")
    client = _ensure_module("database._client")
    client.document_id_from_seed = lambda *_args, **_kwargs: "stubbed-doc-id"

    if "utils.apps" not in sys.modules:
        created.append("utils.apps")
    apps = _ensure_module("utils.apps")
    apps.update_personas_async = lambda *_args, **_kwargs: None

    if "utils.llm.memories" not in sys.modules:
        created.append("utils.llm.memories")
    llm_memories = _ensure_module("utils.llm.memories")
    llm_memories.identify_category_for_memory = lambda *_args, **_kwargs: "other"

    if "utils.notifications" not in sys.modules:
        created.append("utils.notifications")
    notifications = _ensure_module("utils.notifications")
    notifications.send_action_item_data_message = lambda *_args, **_kwargs: None
    notifications.send_action_item_update_message = lambda *_args, **_kwargs: None
    notifications.send_action_item_deletion_message = lambda *_args, **_kwargs: None

    if "dependencies" not in sys.modules:
        created.append("dependencies")
    dependencies = _ensure_module("dependencies")
    dependencies.get_uid_from_mcp_api_key = lambda *_args, **_kwargs: "user-123"
    dependencies.get_current_user_id = lambda *_args, **_kwargs: "user-123"

    return created

def load_mcp_router():
    created = install_mcp_stubs()
    module = importlib.import_module("routers.mcp")
    for name in created:
        sys.modules.pop(name, None)
    return module


def load_mcp_sse():
    created = install_mcp_stubs()
    module = importlib.import_module("routers.mcp_sse")
    for name in created:
        sys.modules.pop(name, None)
    return module
