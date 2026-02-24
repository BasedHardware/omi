import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/agent.dart';
import 'package:omi/env/env.dart';

Future<AgentVmInfo?> getAgentVmStatus() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/agent/vm-status',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  if (response.statusCode == 200) {
    return AgentVmInfo.fromJson(jsonDecode(response.body));
  }
  return null;
}
