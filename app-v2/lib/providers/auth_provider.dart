import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart' show FirebaseAuth, User;
import 'package:flutter/foundation.dart';

import 'package:nooto_v2/env_flags.dart';
import 'package:nooto_v2/services/auth_service.dart';

/// Wraps Firebase auth state changes so the rest of the app can listen via
/// Provider without depending on Firebase directly. Until Task #12 wires up
/// the v2 Firebase bundle IDs, [kEnableFirebaseAuth] keeps Firebase out of
/// the boot path and we run with a local dev "signed-in" toggle.
class AuthChangeProvider extends ChangeNotifier {
  AuthChangeProvider() {
    if (kEnableFirebaseAuth) {
      _sub = FirebaseAuth.instance.authStateChanges().listen((_) => notifyListeners());
    }
  }

  StreamSubscription<User?>? _sub;
  bool _devSignedIn = false;
  String _devName = 'Dev';

  bool get isSignedIn {
    if (kEnableFirebaseAuth) return AuthService.instance.isSignedIn();
    return _devSignedIn;
  }

  String? get displayName {
    if (kEnableFirebaseAuth) {
      final n = AuthService.instance.currentUser?.displayName?.trim();
      if (n == null || n.isEmpty) return null;
      return n;
    }
    return _devName;
  }

  /// Used by the welcome screen during Phase 1 to skip Firebase auth.
  void devSignIn({String? name}) {
    _devSignedIn = true;
    if (name != null && name.isNotEmpty) _devName = name;
    notifyListeners();
  }

  Future<void> signOut() async {
    if (kEnableFirebaseAuth) {
      await AuthService.instance.signOut();
    } else {
      _devSignedIn = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }
}
