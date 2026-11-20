{{- define "workerd.image" -}}
{{- if ne .Release.Namespace "dev-omi-backend" -}}
{{- fail "workerd is dev-only and requires the dev-omi-backend namespace" -}}
{{- end -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" .Values.image.digest) -}}
{{- fail "image.digest must pin the published dev workerd image" -}}
{{- end -}}
gcr.io/based-hardware-dev/workerd@{{ .Values.image.digest }}
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
