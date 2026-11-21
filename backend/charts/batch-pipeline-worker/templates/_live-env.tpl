{{/* Return selected, non-private env entries from the live container. */}}
{{- define "batch-pipeline-worker.liveEnv" -}}
{{- $entries := list -}}
{{- $found := false -}}
{{- range .deployment.spec.template.spec.containers -}}
  {{- if eq .name $.container -}}
    {{- $found = true -}}
    {{- range .env -}}
      {{- if and (ne .name "BATCH_PIPELINE_UID_ALLOWLIST") (has .name $.names) -}}
        {{- $entries = append $entries . -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- if not $found -}}
  {{- fail (printf "Deployment %s has no %s container to preserve env from" .deployment.metadata.name .container) -}}
{{- end -}}
{{- toYaml $entries -}}
{{- end -}}

{{- define "batch-pipeline-worker.allowlistKind" -}}
{{- $kind := "absent" -}}
{{- range . -}}
  {{- if eq .name "BATCH_PIPELINE_UID_ALLOWLIST" -}}
    {{- if .valueFrom -}}
      {{- $kind = "reference" -}}
    {{- else if .value -}}
      {{- $kind = "literal" -}}
    {{- else -}}
      {{- $kind = "empty" -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- $kind -}}
{{- end -}}
