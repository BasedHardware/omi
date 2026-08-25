// Phase 4.1 SKIPPED — not a pure 1:1 wrapper, so not typedef'd here.
// GeneratedAgentVmInfo (gen/agent_wire.g.dart) only carries `hasVm` + `status`, but
// this class also reads/emits `ip` + `auth_token` (VM provisioning fields the
// generated type omits), exposes a `fromJsonBody` convenience factory, and merges the
// extra keys in `toJson`. Typedefing would silently drop those wire fields. To make
// this a typedef candidate, regenerate the wire model to include ip/auth_token.

import 'dart:convert';

import 'package:omi/backend/schema/gen/agent_wire.g.dart' as wire;

class AgentVmInfo {
  final bool hasVm;
  final String? ip;
  final String? authToken;
  final String? status;

  AgentVmInfo({required this.hasVm, this.ip, this.authToken, this.status});

  factory AgentVmInfo.fromJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedAgentVmInfo.fromJson(json);
    return AgentVmInfo(
      hasVm: generated.hasVm,
      status: generated.status,
      ip: json['ip'] as String?,
      authToken: json['auth_token'] as String?,
    );
  }

  factory AgentVmInfo.fromJsonBody(String body) {
    return AgentVmInfo.fromJson(jsonDecode(body) as Map<String, dynamic>);
  }

  factory AgentVmInfo.fromGenerated(wire.GeneratedAgentVmInfo generated) {
    return AgentVmInfo(hasVm: generated.hasVm, status: generated.status);
  }

  wire.GeneratedAgentVmInfo toGenerated() {
    return wire.GeneratedAgentVmInfo(hasVm: hasVm, status: status);
  }

  Map<String, dynamic> toJson() {
    return {...toGenerated().toJson(), 'ip': ip, 'auth_token': authToken};
  }
}
