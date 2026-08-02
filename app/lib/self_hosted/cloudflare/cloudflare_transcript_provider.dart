import 'package:flutter/foundation.dart';

import 'cloudflare_transcript_api.dart';
import 'cloudflare_transcript_models.dart';

class CloudflareTranscriptProvider extends ChangeNotifier {
  CloudflareTranscriptProvider({CloudflareTranscriptApi? api}) : _api = api ?? CloudflareTranscriptHttpApi();

  final CloudflareTranscriptApi _api;
  bool isLoading = false;
  String? error;
  List<CloudflareTranscriptSession> sessions = const [];

  bool get enabled => _api.enabled;

  Future<void> loadSessions() async {
    if (!enabled || isLoading) return;
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      sessions = await _api.listSessions();
    } catch (exception) {
      error = exception.toString();
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<CloudflareTranscriptDetail> loadTranscript(String sessionId) => _api.getTranscript(sessionId);
}
