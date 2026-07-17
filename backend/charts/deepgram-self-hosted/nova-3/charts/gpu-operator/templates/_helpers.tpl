{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "gpu-operator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "gpu-operator.fullname" -}}
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
{{- define "gpu-operator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}

{{- define "gpu-operator.labels" -}}
app.kubernetes.io/name: {{ include "gpu-operator.name" . }}
helm.sh/chart: {{ include "gpu-operator.chart" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- if .Values.operator.labels }}
{{ toYaml .Values.operator.labels }}
{{- end }}
{{- end -}}

{{- define "gpu-operator.operand-labels" -}}
helm.sh/chart: {{ include "gpu-operator.chart" . }}
app.kubernetes.io/managed-by: {{ include "gpu-operator.name" . }}
{{- if .Values.daemonsets.labels }}
{{ toYaml .Values.daemonsets.labels }}
{{- end }}
{{- end -}}

{{- define "gpu-operator.matchLabels" -}}
app.kubernetes.io/name: {{ include "gpu-operator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Full image name with tag
*/}}
{{- define "gpu-operator.fullimage" -}}
{{- .Values.operator.repository -}}/{{- .Values.operator.image -}}:{{- .Values.operator.version | default .Chart.AppVersion -}}
{{- end }}

{{/*
Full image name with tag
*/}}
{{- define "driver-manager.fullimage" -}}
{{- .Values.driver.manager.repository -}}/{{- .Values.driver.manager.image -}}:{{- .Values.driver.manager.version -}}
{{- end }}
