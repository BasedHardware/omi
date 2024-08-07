1 import 'dart:convert';
2 import 'dart:io';
3 
4 import 'package:flutter/material.dart';
5 import 'package:friend_private/backend/http/shared.dart';
6 import 'package:friend_private/backend/database/transcript_segment.dart';
7 import 'package:friend_private/backend/preferences.dart';
8 import 'package:friend_private/backend/schema/memory.dart';
9 import 'package:instabug_flutter/instabug_flutter.dart';
10 
11 Future<String> webhookOnMemoryCreatedCall(ServerMemory? memory, {bool returnRawBody = false}) async {
12   if (memory == null) return '';
13   debugPrint('devModeWebhookCall: $memory');
14   String url = SharedPreferencesUtil().webhookOnMemoryCreated;
15   if (url.isEmpty) return '';
16   if (url.contains('?')) {
17     url += '&uid=${SharedPreferencesUtil().uid}';
18   } else {
19     url += '?uid=${SharedPreferencesUtil().uid}';
20   }
21   debugPrint('triggerMemoryRequestAtEndpoint: $url');
22   var data = memory.toJson();
23   // data['recordingFileBase64'] = await wavToBase64(memory.recordingFilePath ?? '');
24   try {
25     var response = await makeApiCall(
26       url: url,
27       headers: {'Content-Type': 'application/json'},
28       body: jsonEncode(data),
29       method: 'POST',
30     );
31     debugPrint('response: ${response?.statusCode}');
32     if (returnRawBody) return jsonEncode({'statusCode': response?.statusCode, 'body': response?.body});
33 
34     var body = jsonDecode(response?.body ?? '{}');
35     print(body);
36     return body['message'] ?? '';
37   } catch (e) {
38     debugPrint('Error triggering memory request at endpoint: $e');
39     // TODO: is it bad for reporting?  I imagine most of the time is backend error, so nah.
40     CrashReporting.reportHandledCrash(e, StackTrace.current, level: NonFatalExceptionLevel.info, userAttributes: {
41       'url': url,
42     });
43     return '';
44   }
45 }
46 
47 Future<String> webhookOnTranscriptReceivedCall(List<TranscriptSegment> segments, String sessionId) async {
48   debugPrint('webhookOnTranscriptReceivedCall: $segments');
49   return triggerTranscriptSegmentsRequest(SharedPreferencesUtil().webhookOnTranscriptReceived, sessionId, segments);
50 }
51 
52 
53 Future<String> triggerTranscriptSegmentsRequest(String url, String sessionId, List<TranscriptSegment> segments) async {
54   debugPrint('triggerMemoryRequestAtEndpoint: $url');
55   if (url.isEmpty) return '';
56   if (url.contains('?')) {
57     url += '&uid=${SharedPreferencesUtil().uid}';
58   } else {
59     url += '?uid=${SharedPreferencesUtil().uid}';
60   }
61   try {
62     var response = await makeApiCall(
63       url: url,
64       headers: {'Content-Type': 'application/json'},
65       body: jsonEncode({
66         'session_id': sessionId,
67         'segments': segments.map((e) => e.toJson()).toList(),
68       }),
69       method: 'POST',
70     );
71     debugPrint('response: ${response?.statusCode}');
72     var body = jsonDecode(response?.body ?? '{}');
73     print(body);
74     return body['message'] ?? '';
75   } catch (e) {
76     debugPrint('Error triggering transcript request at endpoint: $e');
77     // TODO: is it bad for reporting?  I imagine most of the time is backend error, so nah.
78     CrashReporting.reportHandledCrash(e, StackTrace.current, level: NonFatalExceptionLevel.info, userAttributes: {
79       'url': url,
80     });
81     return '';
82   }
83 }
84 
85 Future<String?> wavToBase64(String filePath) async {
86   if (filePath.isEmpty) return null;
87   try {
88     // Read file as bytes
89     File file = File(filePath);
90     if (!file.existsSync()) {
91       // print('File does not exist: $filePath');
92       return null;
93     }
94     List<int> fileBytes = await file.readAsBytes();
95 
96     // Encode bytes to base64
97     String base64Encoded = base64Encode(fileBytes);
98 
99     return base64Encoded;
100   } catch (e) {
101     // print('Error converting WAV to base64: $e');
102     return null; // Handle error gracefully in your application
103   }
104 }
105 
106 Future<String> webhookOnGoogleCalendarEventCreated(ServerMemory? memory) async {
107   if (memory == null) return '';
108   debugPrint('webhookOnGoogleCalendarEventCreated: $memory');
109   String url = 'https://your-plugin-url.com/google_calendar';
110   if (url.contains('?')) {
111     url += '&uid=${SharedPreferencesUtil().uid}';
112   } else {
113     url += '?uid=${SharedPreferencesUtil().uid}';
114   }
115   debugPrint('triggerGoogleCalendarEventRequestAtEndpoint: $url');
116   var data = memory.toJson();
117   try {
118     var response = await makeApiCall(
119       url: url,
120       headers: {'Content-Type': 'application/json'},
121       body: jsonEncode(data),
122       method: 'POST',
123     );
124     debugPrint('response: ${response?.statusCode}');
125     var body = jsonDecode(response?.body ?? '{}');
126     print(body);
127     return body['message'] ?? '';
128   } catch (e) {
129     debugPrint('Error triggering Google Calendar event request at endpoint: $e');
130     CrashReporting.reportHandledCrash(e, StackTrace.current, level: NonFatalExceptionLevel.info, userAttributes: {
131       'url': url,
132     });
133     return '';
134   }
135 }
