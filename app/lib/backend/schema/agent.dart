class AgentVmInfo {
  final bool hasVm;
  final String? ip;
  final String? authToken;
  final String? status;

  AgentVmInfo({
    required this.hasVm,
    this.ip,
    this.authToken,
    this.status,
  });

  factory AgentVmInfo.fromJson(Map<String, dynamic> json) {
    return AgentVmInfo(
      hasVm: json['has_vm'] ?? false,
      ip: json['ip'],
      authToken: json['auth_token'],
      status: json['status'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'has_vm': hasVm,
      'ip': ip,
      'auth_token': authToken,
      'status': status,
    };
  }
}
