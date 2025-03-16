import 'dart:io' as io;
import 'package:flutter/foundation.dart' show kIsWeb;

class PlatformUtils {
  static bool get isWeb => kIsWeb;
  static bool get isIOS => !kIsWeb && io.Platform.isIOS;
  static bool get isAndroid => !kIsWeb && io.Platform.isAndroid;
  static bool get isMobile => isIOS || isAndroid;
}
