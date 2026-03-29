import 'package:flutter/material.dart';

/// Global navigator key used throughout the app for context access outside the widget tree.
/// Extracted from MyApp to break the transitive dependency on main.dart (and its codegen imports)
/// so that tests can compile without running build_runner.
final GlobalKey<NavigatorState> globalNavigatorKey = GlobalKey<NavigatorState>();
