from scripts.validate_agent_vm_reconciler_scheduler import target_uri, validate_scheduler_state


def test_reconciler_scheduler_requires_five_minute_post_trigger():
    state = {
        "name": "projects/based-hardware-dev/locations/us-central1/jobs/agent-vm-reconciler-5m",
        "state": "ENABLED",
        "schedule": "*/5 * * * *",
        "timeZone": "Etc/UTC",
        "httpTarget": {
            "httpMethod": "POST",
            "uri": target_uri("based-hardware-dev", "us-central1", "agent-vm-reconciler"),
            "oauthToken": {"serviceAccountEmail": "scheduler@based-hardware-dev.iam.gserviceaccount.com"},
        },
    }
    assert (
        validate_scheduler_state(
            state,
            project="based-hardware-dev",
            region="us-central1",
            scheduler_job="agent-vm-reconciler-5m",
            cloud_run_job="agent-vm-reconciler",
            scheduler_service_account="scheduler@based-hardware-dev.iam.gserviceaccount.com",
        )
        == []
    )
    state["schedule"] = "0 * * * *"
    assert validate_scheduler_state(
        state,
        project="based-hardware-dev",
        region="us-central1",
        scheduler_job="agent-vm-reconciler-5m",
        cloud_run_job="agent-vm-reconciler",
        scheduler_service_account="scheduler@based-hardware-dev.iam.gserviceaccount.com",
    )
