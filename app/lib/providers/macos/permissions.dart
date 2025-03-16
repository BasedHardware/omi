import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

// const _dylibPath = '/System/Library/Frameworks/AVFAudio.framework/Versions/Current/AVCaptureDevice';

class Permissions {
  static const platform = MethodChannel("com.omi.friend/permissions");

  void request() async {
    try {
      final access = await platform.invokeMethod<bool>("microphone");
      print("access is $access");
    } on PlatformException catch (e) {
      debugPrint(e.message);
    }
  }
}
