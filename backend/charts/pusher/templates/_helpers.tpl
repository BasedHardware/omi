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

{{/*
SCA-4463: a Pusher-only record token lease vector. Empty (the default) renders
nothing and the four lease keys keep their configMapKeyRef to the shared
runtime ConfigMap. Set, it replaces those four entries on this container with
literal values; container env wins over envFrom, and the shared ConfigMap and
backend-listen are untouched. Release supplies it per dispatch.
*/}}
{{- define "pusher.recordTokenLeaseOverrideNames" -}}
RECORD_TOKEN_LEASE_MODE RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT RECORD_TOKEN_LEASE_SECONDS RECORD_TOKEN_LEASE_DEPLOYED_AT
{{- end -}}

{{- define "pusher.recordTokenLeaseOverrideEnv" -}}
{{- $lease := .Values.recordTokenLeaseOverride -}}
{{- if not (kindIs "map" $lease) -}}
  {{- fail "recordTokenLeaseOverride must be a map" -}}
{{- end -}}
{{- $keys := list "mode" "servePercent" "seconds" "deployedAt" -}}
{{- if ne (keys $lease | sortAlpha | join ",") ($keys | sortAlpha | join ",") -}}
  {{- fail "recordTokenLeaseOverride requires exactly mode, servePercent, seconds and deployedAt" -}}
{{- end -}}
{{- range $key := $keys -}}
  {{- if not (kindIs "string" (get $lease $key)) -}}
    {{- fail (printf "recordTokenLeaseOverride.%s must be a string" $key) -}}
  {{- end -}}
{{- end -}}
{{- /* Serve is reached only through the coordinated shared ConfigMap ramp. */ -}}
{{- if not (has $lease.mode (list "off" "shadow")) -}}
  {{- fail "recordTokenLeaseOverride.mode must be off or shadow; serve is reached only through the coordinated shared ramp" -}}
{{- end -}}
{{- if ne $lease.servePercent "0" -}}
  {{- fail "recordTokenLeaseOverride.servePercent must be exactly 0; serve is reached only through the coordinated shared ramp" -}}
{{- end -}}
{{- if or (not (regexMatch "^[1-9][0-9]{3}$" $lease.seconds)) (lt (atoi $lease.seconds) 1800) (gt (atoi $lease.seconds) 7200) -}}
  {{- fail "recordTokenLeaseOverride.seconds must be an integer from 1800 to 7200" -}}
{{- end -}}
{{- if not (regexMatch "^(0|[1-9][0-9]{0,11})$" $lease.deployedAt) -}}
  {{- fail "recordTokenLeaseOverride.deployedAt must be a non-negative integer epoch" -}}
{{- end -}}
{{- if and (ne $lease.mode "off") (eq $lease.deployedAt "0") -}}
  {{- fail "recordTokenLeaseOverride.deployedAt must pin a shared release epoch before shadow" -}}
{{- end -}}
- name: RECORD_TOKEN_LEASE_MODE
  value: {{ $lease.mode | quote }}
- name: RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT
  value: {{ $lease.servePercent | quote }}
- name: RECORD_TOKEN_LEASE_SECONDS
  value: {{ $lease.seconds | quote }}
- name: RECORD_TOKEN_LEASE_DEPLOYED_AT
  value: {{ $lease.deployedAt | quote }}
{{- end -}}
