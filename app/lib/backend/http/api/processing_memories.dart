import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/schema/geolocation.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/env/env.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

Future<UpdateProcessingMemoryResponse?> updateProcessingMemoryServer({
  required String id,
  Geolocation? geolocation,
  bool emotionalFeedback = false,
}) async {
  // Body
  var bodyData = <String, dynamic>{};
  bodyData.addAll({
    'emotional_feedback': emotionalFeedback,
  });
  if (geolocation != null) {
    bodyData.addAll({"geolocation": geolocation.toJson()});
  }

  debugPrint(jsonEncode(bodyData));

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/processing-memories/$id',
    headers: {},
    method: 'PATCH',
    body: jsonEncode(bodyData),
  );
  if (response == null) return null;
  debugPrint('updateProcessingMemoryServer: ${response.body}');
  if (response.statusCode == 200) {
    return UpdateProcessingMemoryResponse.fromJson(jsonDecode(response.body));
  } else {
    // TODO: Server returns 304 doesn't recover
    CrashReporting.reportHandledCrash(
      Exception('Failed to create memory'),
      StackTrace.current,
      level: NonFatalExceptionLevel.info,
      userAttributes: {
        'response': response.body,
      },
    );
  }
  return null;
}
