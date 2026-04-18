## Logs

### Flutter (iOS Simulator)
Flutter logs are whatever file you redirect `flutter run` stdout into. The repo uses both
`/tmp/flutter-run.log` and `/tmp/omi-flutter.log` in different workflows, so treat the path below
as an example command convention rather than a fixed app log sink. Use `print()` (not
`Logger.debug`) for logs that must appear there. Grep with `[TagName]` prefixes:
```bash
grep -E "\[AgentChat\]|\[HomePage\]" /tmp/flutter-run.log | tail -20
```

### Backend-listen (GKE, namespace `prod-omi-backend`)
```bash
kubectl logs -n prod-omi-backend -l app.kubernetes.io/instance=prod-omi-backend-listen --timestamps --since=10m | grep "<uid>"
```

### Agent-proxy (GKE, namespace `prod-omi-backend`)
```bash
kubectl logs -n prod-omi-backend -l app.kubernetes.io/instance=prod-omi-agent-proxy --timestamps --since=10m | grep "<uid>"
```

### Agent VM
```bash
gcloud compute ssh omi-agent-<id> --zone=us-central1-a --project=based-hardware \
  --command="journalctl -u omi-agent --no-pager --since '10 minutes ago' | grep -E 'Client|Query|Prewarm|session|disconnect|error|Persistent'"
```

### Agent Chat Debugging
For end-to-end debugging of the mobile agent chat pipeline (phone → agent-proxy → VM), see the `ai-chat-debug` skill.
