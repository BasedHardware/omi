import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/agent.dart';
import 'package:omi/utils/logger.dart';

/// Agent VM endpoints always hit prod — VMs and Firestore are in the prod project only.
const _agentApiBase = 'https://api.omi.me/';

Future<AgentVmInfo?> getAgentVmStatus() async {
  var response = await makeApiCall(
    url: '${_agentApiBase}v1/agent/vm-status',
    headers: {'Authorization': await getAuthHeader()},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  if (response.statusCode == 200) {
    return AgentVmInfo.fromJson(jsonDecode(response.body));
  }
  return null;
}

Future<void> ensureAgentVm() async {
  try {
    await makeApiCall(
      url: '${_agentApiBase}v1/agent/vm-ensure',
      headers: {'Authorization': await getAuthHeader()},
      method: 'POST',
      body: '',
    );
  } catch (e) {
    Logger.debug('ensureAgentVm failed: $e');
  }
}

Future<void> sendAgentKeepalive() async {
  try {
    await makeApiCall(
      url: '${_agentApiBase}v1/agent/keepalive',
      headers: {'Authorization': await getAuthHeader()},
      method: 'POST',
      body: '',
    );
  } catch (e) {
    Logger.debug('sendAgentKeepalive failed: $e');
  }
}
