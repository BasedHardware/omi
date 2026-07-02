import 'package:omi/backend/schema/gen/agent_wire.g.dart' as wire;

class AgentVmInfo {
  final bool hasVm;
  final String? ip;
  final String? authToken;
  final String? status;

  AgentVmInfo({required this.hasVm, this.ip, this.authToken, this.status});

  factory AgentVmInfo.fromJson(Map<String, dynamic> json) {
    return AgentVmInfo.fromGenerated(wire.GeneratedAgentVmInfo.fromJson(json));
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
