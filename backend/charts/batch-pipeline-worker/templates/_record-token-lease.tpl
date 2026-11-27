{{- define "batch-pipeline-worker.recordTokenLeaseGuard" -}}
{{- /* SCA-3748: prod values leave the vector empty so a render without the deploy's
       --set-string of vars.RECORD_TOKEN_LEASE_* fails instead of pinning a stale epoch. */ -}}
{{- range $key := list "mode" "servePercent" "seconds" "deployedAt" -}}
{{- $value := index $.Values.recordTokenLease $key -}}
{{- if or (kindIs "invalid" $value) (eq (toString $value) "") -}}
{{- fail (printf "recordTokenLease.%s is required: pass --set-string from vars.RECORD_TOKEN_LEASE_* (SCA-3748)" $key) -}}
{{- end -}}
{{- end -}}
{{- if not (has .Values.recordTokenLease.mode (list "off" "shadow" "serve")) -}}
{{- fail "recordTokenLease.mode must be off, shadow or serve" -}}
{{- end -}}
{{- if and (ne .Values.recordTokenLease.mode "off") (le (float64 .Values.recordTokenLease.deployedAt) 0.0) -}}
{{- fail "recordTokenLease.deployedAt must pin a shared release epoch before shadow/serve" -}}
{{- end -}}
{{- end -}}
