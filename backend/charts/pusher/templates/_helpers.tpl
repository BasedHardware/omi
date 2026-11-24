{{/*
Expand the name of the chart.
*/}}
{{- define "pusher.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "pusher.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "pusher.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "pusher.labels" -}}
helm.sh/chart: {{ include "pusher.chart" . }}
{{ include "pusher.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "pusher.selectorLabels" -}}
app.kubernetes.io/name: {{ include "pusher.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "pusher.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "pusher.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "pusher.conversationsV3StartupEnv" -}}
{{- $env := .Values.conversationsV3StartupEnv -}}
{{- if not (kindIs "map" $env) -}}
  {{- fail "conversationsV3StartupEnv must be a map" -}}
{{- end -}}
{{- $required := list "CONVERSATIONS_V3" "CONVERSATIONS_V3_STAGE" "SYNC_TASKS_PROJECT" "SYNC_TASKS_LOCATION" "SYNC_TASKS_INVOKER_SA" -}}
{{- $targets := list "CONVERSATIONS_V3_TASKS_URL" "SYNC_TASKS_HANDLER_URL" -}}
{{- range $key := concat $required $targets -}}
  {{- $value := get $env $key -}}
  {{- if or (not (hasKey $env $key)) (not (kindIs "string" $value)) -}}
    {{- fail (printf "conversationsV3StartupEnv.%s must be an explicit string" $key) -}}
  {{- end -}}
  {{- if or (contains "$(" $value) (contains "$$" $value) (and (has $key $required) (empty (trim $value))) -}}
    {{- fail (printf "conversationsV3StartupEnv.%s must be a literal startup value" $key) -}}
  {{- end -}}
{{- end -}}
{{- if ne (len $env) 7 -}}
  {{- fail "conversationsV3StartupEnv accepts only the seven conversations-v3 startup keys" -}}
{{- end -}}
{{- if and (empty (trim $env.CONVERSATIONS_V3_TASKS_URL)) (empty (trim $env.SYNC_TASKS_HANDLER_URL)) -}}
  {{- fail "conversationsV3StartupEnv requires a task target" -}}
{{- end -}}
{{- range $key, $value := $env }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end -}}
{{- end -}}
