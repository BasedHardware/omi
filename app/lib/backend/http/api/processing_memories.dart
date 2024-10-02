import 'dart:convert';

import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/env/env.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

Future<ProcessingMemoryResponse?> fetchProcessingMemoryServer({required String id}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/processing-memories/$id',
    headers: {},
    method: 'GET',
    body: "",
  );
  if (response == null) return null;
  if (response.statusCode == 200) {
    return ProcessingMemoryResponse.fromJson(jsonDecode(response.body));
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
