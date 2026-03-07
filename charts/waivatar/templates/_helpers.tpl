{{- define "waivatar.name" -}}
{{- default .Chart.Name .Values.nameOverride -}}
{{- end -}}

{{- define "waivatar.fullname" -}}
{{- printf "%s-%s" (include "waivatar.name" .) .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
