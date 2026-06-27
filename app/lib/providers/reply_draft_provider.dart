import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/reply_drafts.dart';
import 'package:omi/backend/schema/reply_draft.dart';

class ReplyDraftProvider extends ChangeNotifier {
  bool isLoading = false;
  String? error;
  ReplyDraftResponse? draft;

  Future<void> generate(ReplyDraftRequest request) async {
    if (request.incomingMessage.trim().isEmpty) {
      error = 'Paste the message you want to answer first.';
      notifyListeners();
      return;
    }

    isLoading = true;
    error = null;
    notifyListeners();

    try {
      draft = await createReplyDraftServer(request);
    } catch (e) {
      error = e.toString().replaceFirst('Exception: ', '');
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  void clear() {
    error = null;
    draft = null;
    notifyListeners();
  }
}
