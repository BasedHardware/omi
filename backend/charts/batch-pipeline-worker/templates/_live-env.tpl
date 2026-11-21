{{/* Return the selected env entries from an existing Deployment's named container.
     Copy the env objects so empty literals, references and absent keys stay as-is. */}}
{{- define "batch-pipeline-worker.liveEnv" -}}
{{- $entries := list -}}
{{- $found := false -}}
{{- range .deployment.spec.template.spec.containers -}}
  {{- if eq .name $.container -}}
    {{- $found = true -}}
    {{- range .env -}}
      {{- if has .name $.names -}}
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
