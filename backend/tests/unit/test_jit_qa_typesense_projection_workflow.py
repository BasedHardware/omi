from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".." / ".github" / "workflows" / "jit_qa_typesense_projection.yml"


def _rehydrate_steps():
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["rehydrate"]["steps"]


def test_rehydrate_authenticates_docker_before_pulling_private_runner_image():
    steps = _rehydrate_steps()
    auth_index = next(
        index for index, step in enumerate(steps) if step.get("name") == "Authenticate Docker to Artifact Registry"
    )
    auth_step = steps[auth_index]
    assert auth_step["run"] == "gcloud auth configure-docker gcr.io --quiet"
    assert auth_index < next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Run canonical rebuild and real search_knowledge proof"
    )
