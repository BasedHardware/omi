import '/backend/api_requests/api_calls.dart';
import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/custom_code/actions/index.dart' as actions;
import 'device_data_widget.dart' show DeviceDataWidget;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class DeviceDataModel extends FlutterFlowModel<DeviceDataWidget> {
  ///  Local state fields for this component.

  List<String> whispers = [];
  void addToWhispers(String item) => whispers.add(item);
  void removeFromWhispers(String item) => whispers.remove(item);
  void removeAtIndexFromWhispers(int index) => whispers.removeAt(index);
  void insertAtIndexInWhispers(int index, String item) =>
      whispers.insert(index, item);
  void updateWhispersAtIndex(int index, Function(String) updateFn) =>
      whispers[index] = updateFn(whispers[index]);

  List<int> ints = [];
  void addToInts(int item) => ints.add(item);
  void removeFromInts(int item) => ints.remove(item);
  void removeAtIndexFromInts(int index) => ints.removeAt(index);
  void insertAtIndexInInts(int index, int item) => ints.insert(index, item);
  void updateIntsAtIndex(int index, Function(int) updateFn) =>
      ints[index] = updateFn(ints[index]);

  ///  State fields for stateful widgets in this component.

  // Stores action output result for [Custom Action - bleReceiveWAV] action in deviceData widget.
  FFUploadedFile? wav;
  // Stores action output result for [Backend Call - API (WHISPER D)] action in deviceData widget.
  ApiCallResponse? whsiper;

  /// Initialization and disposal methods.

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {}

  /// Action blocks are added here.

  /// Additional helper methods are added here.
}
