{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "cluster-autoscaler.name" -}}
{{- default (printf "%s-%s" .Values.cloudProvider .Chart.Name) .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
*/}}
{{- define "cluster-autoscaler.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default (printf "%s-%s" .Values.cloudProvider .Chart.Name) .Values.nameOverride -}}
{{- if ne $name .Release.Name -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s" $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "cluster-autoscaler.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Return instance and name labels.
*/}}
{{- define "cluster-autoscaler.instance-name" -}}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/name: {{ include "cluster-autoscaler.name" . | quote }}
{{- end -}}


{{/*
Return labels, including instance and name.
*/}}
{{- define "cluster-autoscaler.labels" -}}
{{ include "cluster-autoscaler.instance-name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
helm.sh/chart: {{ include "cluster-autoscaler.chart" . | quote }}
{{- if .Values.additionalLabels }}
{{ toYaml .Values.additionalLabels }}
{{- end -}}
{{- end -}}

{{/*
Return the appropriate apiVersion for deployment.
*/}}
{{- define "deployment.apiVersion" -}}
{{- $kubeTargetVersion := default .Capabilities.KubeVersion.GitVersion .Values.kubeTargetVersionOverride }}
{{- if semverCompare "<1.9-0" $kubeTargetVersion -}}
{{- print "apps/v1beta2" -}}
{{- else -}}
{{- print "apps/v1" -}}
{{- end -}}
{{- end -}}

{{/*
Return the appropriate apiVersion for podsecuritypolicy.
*/}}
{{- define "podsecuritypolicy.apiVersion" -}}
{{- $kubeTargetVersion := default .Capabilities.KubeVersion.GitVersion .Values.kubeTargetVersionOverride }}
{{- if semverCompare "<1.10-0" $kubeTargetVersion -}}
{{- print "extensions/v1beta1" -}}
{{- else -}}
{{- print "policy/v1beta1" -}}
{{- end -}}
{{- end -}}

{{/*
Return the appropriate apiVersion for podDisruptionBudget.
*/}}
{{- define "podDisruptionBudget.apiVersion" -}}
{{- $kubeTargetVersion := default .Capabilities.KubeVersion.GitVersion .Values.kubeTargetVersionOverride }}
{{- if semverCompare "<1.21-0" $kubeTargetVersion -}}
{{- print "policy/v1beta1" -}}
{{- else -}}
{{- print "policy/v1" -}}
{{- end -}}
{{- end -}}

{{/*
Return the service account name used by the pod.
*/}}
{{- define "cluster-autoscaler.serviceAccountName" -}}
{{- if .Values.rbac.serviceAccount.create -}}
    {{ default (include "cluster-autoscaler.fullname" .) .Values.rbac.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.rbac.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return true if the priority expander is enabled
*/}}
{{- define "cluster-autoscaler.priorityExpanderEnabled" -}}
{{- $expanders := splitList "," (default "" .Values.extraArgs.expander) -}}
{{- if has "priority" $expanders -}}
{{- true -}}
{{- end -}}
{{- end -}}

{{/*
autoDiscovery.clusterName for clusterapi.
*/}}
{{- define "cluster-autoscaler.capiAutodiscovery.clusterName" -}}
{{- print "clusterName=" -}}{{ tpl (.Values.autoDiscovery.clusterName) . }}
{{- end -}}

{{/*
autoDiscovery.namespace for clusterapi.
*/}}
{{- define "cluster-autoscaler.capiAutodiscovery.namespace" -}}
{{- print "namespace=" }}{{ .Values.autoDiscovery.namespace -}}
{{- end -}}

{{/*
autoDiscovery.labels for clusterapi.
*/}}
{{- define "cluster-autoscaler.capiAutodiscovery.labels" -}}
{{- range $i, $el := .Values.autoDiscovery.labels -}}
{{- if $i -}}{{- print "," -}}{{- end -}}
{{- range $key, $val := $el -}}
{{- $key -}}{{- print "=" -}}{{- $val -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Return the autodiscoveryparameters for clusterapi.
*/}}
{{- define "cluster-autoscaler.capiAutodiscoveryConfig" -}}
{{- if .Values.autoDiscovery.clusterName -}}
{{ include "cluster-autoscaler.capiAutodiscovery.clusterName" . }}
    {{- if .Values.autoDiscovery.namespace }}
    {{- print "," -}}
    {{ include "cluster-autoscaler.capiAutodiscovery.namespace" . }}
    {{- end -}}
    {{- if .Values.autoDiscovery.labels }}
    {{- print "," -}}
    {{ include "cluster-autoscaler.capiAutodiscovery.labels" . }}
    {{- end -}}
{{- else if .Values.autoDiscovery.namespace -}}
{{ include "cluster-autoscaler.capiAutodiscovery.namespace" . }}
    {{- if .Values.autoDiscovery.labels }}
    {{- print "," -}}
    {{ include "cluster-autoscaler.capiAutodiscovery.labels" . }}
    {{- end -}}
{{- else if .Values.autoDiscovery.labels -}}
    {{ include "cluster-autoscaler.capiAutodiscovery.labels" . }}
{{- end -}}
{{- end -}}
