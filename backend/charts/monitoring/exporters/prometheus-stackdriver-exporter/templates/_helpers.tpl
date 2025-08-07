{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "stackdriver-exporter.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "stackdriver-exporter.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "stackdriver-exporter.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "stackdriver-exporter.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
    {{ default (include "stackdriver-exporter.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Generate basic labels
*/}}
{{- define "stackdriver-exporter.labels" }}
helm.sh/chart: {{ template "stackdriver-exporter.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: metrics
app.kubernetes.io/part-of: {{ template "stackdriver-exporter.name" . }}
{{- include "stackdriver-exporter.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
{{- if .Values.customLabels }}
{{ toYaml .Values.customLabels }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "stackdriver-exporter.selectorLabels" }}
app.kubernetes.io/name: {{ include "stackdriver-exporter.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}