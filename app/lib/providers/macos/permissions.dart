import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class Permissions {
  static const platform = MethodChannel("com.omi.friend/permissions");

  void request() async {
    try {
      final access = await platform.invokeMethod<bool>("microphone");
      debugPrint("Microphone access is $access");
    } on PlatformException catch (e) {
      debugPrint(e.message);
    }
  }
}
