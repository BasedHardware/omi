{{- define "batch-pipeline-worker.recordTokenLeaseGuard" -}}
{{- if not (has .Values.recordTokenLease.mode (list "off" "shadow" "serve")) -}}
{{- fail "recordTokenLease.mode must be off, shadow or serve" -}}
{{- end -}}
{{- if and (ne .Values.recordTokenLease.mode "off") (le (float64 .Values.recordTokenLease.deployedAt) 0.0) -}}
{{- fail "recordTokenLease.deployedAt must pin a shared release epoch before shadow/serve" -}}
{{- end -}}
{{- end -}}
