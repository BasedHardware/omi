{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "node-feature-discovery.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "node-feature-discovery.fullname" -}}
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
Allow the release namespace to be overridden for multi-namespace deployments in combined charts
*/}}
{{- define "node-feature-discovery.namespace" -}}
  {{- if .Values.namespaceOverride -}}
    {{- .Values.namespaceOverride -}}
  {{- else -}}
    {{- .Release.Namespace -}}
  {{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "node-feature-discovery.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "node-feature-discovery.labels" -}}
helm.sh/chart: {{ include "node-feature-discovery.chart" . }}
{{ include "node-feature-discovery.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "node-feature-discovery.selectorLabels" -}}
app.kubernetes.io/name: {{ include "node-feature-discovery.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Create the name of the service account which the nfd master will use
*/}}
{{- define "node-feature-discovery.master.serviceAccountName" -}}
{{- if .Values.master.serviceAccount.create -}}
    {{ default (include "node-feature-discovery.fullname" .) .Values.master.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.master.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Create the name of the service account which the nfd worker will use
*/}}
{{- define "node-feature-discovery.worker.serviceAccountName" -}}
{{- if .Values.worker.serviceAccount.create -}}
    {{ default (printf "%s-worker" (include "node-feature-discovery.fullname" .)) .Values.worker.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.worker.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Create the name of the service account which topologyUpdater will use
*/}}
{{- define "node-feature-discovery.topologyUpdater.serviceAccountName" -}}
{{- if .Values.topologyUpdater.serviceAccount.create -}}
    {{ default (printf "%s-topology-updater" (include "node-feature-discovery.fullname" .)) .Values.topologyUpdater.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.topologyUpdater.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Create the name of the service account which nfd-gc will use
*/}}
{{- define "node-feature-discovery.gc.serviceAccountName" -}}
{{- if .Values.gc.serviceAccount.create -}}
    {{ default (printf "%s-gc" (include "node-feature-discovery.fullname" .)) .Values.gc.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.gc.serviceAccount.name }}
{{- end -}}
{{- end -}}
