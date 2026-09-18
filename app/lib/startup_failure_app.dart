import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// Shown when `_init()` throws before the app's first frame.
///
/// Deliberately self-contained: no providers, no services, no theme lookups and
/// no localisation. Everything it could depend on is exactly what may have just
/// failed to initialise, so it must render from nothing but Flutter itself.
///
/// Without this the app sits on the launch storyboard indefinitely — `runApp()`
/// never runs, and `debugPrint` from the zone handler is invisible in profile
/// and release builds. A startup guard rejecting a misconfigured
/// `OMI_API_BASE_URL` is a precise, actionable error; presenting it as a blank
/// splash screen is what made it expensive to diagnose.
class StartupFailureApp extends StatelessWidget {
  const StartupFailureApp({super.key, required this.error, this.stack});

  final Object error;
  final StackTrace? stack;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        backgroundColor: const Color(0xFF000000),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Omi could not start',
                  style: TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Startup configuration was rejected before the app could load. '
                  'This is usually a build-time setting, not a problem with your device.',
                  style: TextStyle(color: Colors.white70, fontSize: 14),
                ),
                const SizedBox(height: 20),
                Expanded(
                  child: SingleChildScrollView(
                    child: SelectableText(
                      // Selectable so the message can be copied off a device
                      // that has no debugger attached — which is the situation
                      // this screen exists for.
                      kDebugMode || kProfileMode ? '$error\n\n$stack' : '$error',
                      style: const TextStyle(color: Color(0xFFFFB4A9), fontSize: 13, height: 1.4),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
