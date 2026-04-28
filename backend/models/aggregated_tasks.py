"""Cross-plugin task shape for the unified Plan/home view.

Each enabled integration plugin (Jira, Linear, …) returns its `list_my_issues`
chat tool with a `data.tasks[]` array of dicts matching `IntegrationTask`. The
backend aggregator (`routers/aggregated_tasks.py`) tags each with the source
app metadata and merges into `AggregatedTasksResponse`. Keep this in sync
with the per-plugin normalizers:

- plugins/nooto-jira-app/routes/tools.py::_normalize_jira_issue
- plugins/omi-linear-app/main.py (inside tool_list_my_issues)
"""

from typing import Optional

from pydantic import BaseModel


class IntegrationTask(BaseModel):
    external_id: str
    title: str
    # Short plain-text snippet of the source description (plugins truncate
    # before sending — usually ~240 chars). Optional; not every plugin
    # surfaces it.
    description: Optional[str] = None
    status: str
    status_type: Optional[str] = None  # "todo" | "in_progress" | "done" | "canceled"
    due_at: Optional[str] = None
    priority: Optional[str] = None
    url: str = ""
    project: Optional[str] = None
    assignee: Optional[str] = None
    updated_at: Optional[str] = None


class NormalizedTask(IntegrationTask):
    source_app_id: str
    source_app_name: str
    source_app_image: Optional[str] = None


class AggregatedTasksResponse(BaseModel):
    tasks: list[NormalizedTask]
    errors: dict[str, str] = {}
