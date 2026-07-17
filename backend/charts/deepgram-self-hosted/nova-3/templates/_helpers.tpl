{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "deepgram-self-hosted.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "deepgram-self-hosted.labels" -}}
app.kubernetes.io/name: "deepgram-self-hosted"
helm.sh/chart: {{ include "deepgram-self-hosted.chart" . }}
{{ include "deepgram-self-hosted.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- range $key, $val := .Values.global.additionalLabels }}
{{ $key }}: {{ $val | quote }}
{{- end}}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "deepgram-self-hosted.selectorLabels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
