import '/backend/api_requests/api_calls.dart';
import '/backend/backend.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/request_manager.dart';

import 'test_new_widget.dart' show TestNewWidget;
import 'package:flutter/material.dart';

class TestNewModel extends FlutterFlowModel<TestNewWidget> {
  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();
  // Stores action output result for [RevenueCat - Purchase] action in Button widget.
  bool? purchased;
  // State field(s) for TextField widget.
  FocusNode? textFieldFocusNode;
  TextEditingController? textController;
  String? Function(BuildContext, String?)? textControllerValidator;
  // Stores action output result for [Backend Call - API (test)] action in Button widget.
  List<String>? devided;

  /// Query cache managers for this widget.

  final _alltestManager = StreamRequestManager<List<MemoriesRecord>>();
  Stream<List<MemoriesRecord>> alltest({
    String? uniqueQueryKey,
    bool? overrideCache,
    required Stream<List<MemoriesRecord>> Function() requestFn,
  }) =>
      _alltestManager.performRequest(
        uniqueQueryKey: uniqueQueryKey,
        overrideCache: overrideCache,
        requestFn: requestFn,
      );
  void clearAlltestCache() => _alltestManager.clear();
  void clearAlltestCacheKey(String? uniqueKey) =>
      _alltestManager.clearRequest(uniqueKey);

  /// Initialization and disposal methods.

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    unfocusNode.dispose();
    textFieldFocusNode?.dispose();
    textController?.dispose();

    /// Dispose query cache managers for this widget.

    clearAlltestCache();
  }

  /// Action blocks are added here.

  /// Additional helper methods are added here.
}
