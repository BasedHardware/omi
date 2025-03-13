// This file provides platform-specific imports and mocks

import 'package:flutter/foundation.dart' show kIsWeb;

// Conditionally export dart:io for non-web platforms
export 'platform_imports_io.dart' if (dart.library.html) 'platform_imports_web.dart';

// Helper method to check if running on web
bool get isRunningOnWeb => kIsWeb;
