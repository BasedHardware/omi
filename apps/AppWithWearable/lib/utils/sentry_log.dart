import 'package:flutter/material.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

addEventToContext(String event) {
  debugPrint(event);
  InstabugLog.logInfo(event);
}
