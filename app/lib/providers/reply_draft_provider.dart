import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/reply_drafts.dart';
import 'package:omi/backend/schema/reply_draft.dart';

class ReplyDraftProvider extends ChangeNotifier {
  bool isLoading = false;
  String? error;
  ReplyDraftResponse? draft;
  int _requestSerial = 0;

  Future<void> generate(ReplyDraftRequest request) async {
    final requestId = ++_requestSerial;

    if (request.incomingMessage.trim().isEmpty) {
      isLoading = false;
      error = 'Paste the message you want to answer first.';
      draft = null;
      notifyListeners();
      return;
    }

    isLoading = true;
    error = null;
    notifyListeners();

    try {
      final response = await createReplyDraftServer(request);
      if (requestId != _requestSerial) return;
      draft = response;
    } catch (e) {
      if (requestId != _requestSerial) return;
      error = e.toString().replaceFirst('Exception: ', '');
    } finally {
      if (requestId == _requestSerial) {
        isLoading = false;
        notifyListeners();
      }
    }
  }

  void clear() {
    _requestSerial++;
    isLoading = false;
    error = null;
    draft = null;
    notifyListeners();
  }
}
