import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/auth/clear_deleted_account_session.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('account deletion invalidates late refresh and clears provider state before storage', () async {
    SharedPreferences.setMockInitialValues({'uid': 'user-1', 'authToken': 'old-token'});
    await SharedPreferencesUtil.init();
    final pendingRefresh = Completer<RefreshedAuthToken?>();
    final gateway = _DeletionGateway(pendingRefresh);
    final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
    final order = <String>[];

    final refresh = service.refreshIdToken();
    await clearDeletedAccountSession(
      authService: service,
      clearUserState: () => order.add('providers'),
      clearWal: () async => order.add('wal'),
      clearPreferences: () async {
        order.add('preferences');
        await SharedPreferencesUtil().clear();
      },
    );
    pendingRefresh.complete(RefreshedAuthToken(token: 'late-token', expirationTime: DateTime.now()));

    expect(await refresh, isA<AuthTokenMissingUser>());
    expect(order, ['providers', 'wal', 'preferences']);
    expect(gateway.signOutCalls, 1);
    expect(SharedPreferencesUtil().uid, isEmpty);
    expect(SharedPreferencesUtil().authToken, isEmpty);
    expect(await service.refreshIdToken(), isA<AuthTokenMissingUser>());
    expect(gateway.refreshCalls, 1, reason: 'the deleted Firebase user must not start another refresh');
  });

  test('account deletion clears WAL and preferences when Firebase sign-out fails', () async {
    SharedPreferences.setMockInitialValues({'uid': 'user-1', 'authToken': 'old-token'});
    await SharedPreferencesUtil.init();
    final gateway = _DeletionGateway(Completer<RefreshedAuthToken?>(), failSignOut: true);
    final service = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
    final order = <String>[];

    await clearDeletedAccountSession(
      authService: service,
      clearUserState: () => order.add('providers'),
      clearWal: () async {
        order.add('wal');
        throw StateError('disk unavailable');
      },
      clearPreferences: () async {
        order.add('preferences');
        await SharedPreferencesUtil().clear();
      },
    );

    expect(order, ['providers', 'wal', 'preferences']);
    expect(gateway.signOutCalls, 1);
    expect(SharedPreferencesUtil().uid, isEmpty);
    expect(SharedPreferencesUtil().authToken, isEmpty);
    expect(await service.refreshIdToken(), isA<AuthTokenMissingUser>());
    expect(gateway.refreshCalls, 0, reason: 'failed platform sign-out must still leave the old user locally terminal');
  });
}

final class _DeletionGateway implements AuthTokenGateway {
  _DeletionGateway(this.pendingRefresh, {this.failSignOut = false});

  final Completer<RefreshedAuthToken?> pendingRefresh;
  final bool failSignOut;
  int signOutCalls = 0;
  int refreshCalls = 0;

  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'user-1');

  @override
  Future<RefreshedAuthToken?> forceRefresh() {
    refreshCalls++;
    return pendingRefresh.future;
  }

  @override
  Future<void> signOut() async {
    signOutCalls++;
    if (failSignOut) throw StateError('Firebase sign-out failed');
  }
}
