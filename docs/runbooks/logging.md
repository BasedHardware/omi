## Logs

### Flutter (iOS Simulator)
App logs go to `/tmp/flutter-run.log`. Use `print()` (not `Logger.debug`) for logs that must appear there. Grep with `[TagName]` prefixes:
```bash
grep -E "\[AgentChat\]|\[HomePage\]" /tmp/flutter-run.log | tail -20
```

### Backend (Cloud Run)
```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="backend-listen"' --project=based-hardware --limit=30 --freshness=5m --format=json
```

### Agent-proxy (GKE, namespace `prod-omi-backend`)
```bash
kubectl logs -n prod-omi-backend -l app=agent-proxy --timestamps --since=10m | grep "<uid>"
```

### Agent VM
```bash
gcloud compute ssh omi-agent-<id> --zone=us-central1-a --project=based-hardware \
  --command="journalctl -u omi-agent --no-pager --since '10 minutes ago' | grep -E 'Client|Query|Prewarm|session|disconnect|error|Persistent'"
```

### Agent Chat Debugging
For end-to-end debugging of the mobile agent chat pipeline (phone → agent-proxy → VM), see the `ai-chat-debug` skill.
