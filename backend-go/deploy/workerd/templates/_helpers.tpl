{{- define "workerd.project" -}}
{{- $projects := dict "dev" "based-hardware-dev" "prod" "based-hardware" -}}
{{- $project := get $projects .Values.environment -}}
{{- if not $project -}}
{{- fail "environment must be dev or prod" -}}
{{- end -}}
{{- if ne .Release.Namespace (printf "%s-omi-backend" .Values.environment) -}}
{{- fail "release namespace must match the workerd environment" -}}
{{- end -}}
{{- $project -}}
{{- end -}}

{{- define "workerd.image" -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" .Values.image.digest) -}}
{{- fail "image.digest must pin the published workerd image" -}}
{{- end -}}
gcr.io/{{ include "workerd.project" . }}/workerd@{{ .Values.image.digest }}
{{- end -}}

{{- define "workerd.labels" -}}
app.kubernetes.io/name: workerd
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "workerd.securityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
{{- end -}}
