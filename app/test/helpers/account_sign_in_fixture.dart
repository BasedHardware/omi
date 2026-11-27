import 'package:firebase_auth/firebase_auth.dart';

import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth_service.dart';

class AccountSignInFixture extends AuthenticationProvider {
  AccountSignInFixture({String providerId = 'apple.com'}) : super(initializeListeners: false) {
    user = _FixtureUser(uid, [providerId]);
  }

  static const uid = 'fixture-account-123';
  static const profile = {'uid': uid, 'givenName': 'Taylor', 'email': 'taylor@example.test'};

  Future<ProviderLinkResult?> Function(String providerId, ProviderLinkAuthorization? authorization)? onLink;
  final linkAttempts = <(String, String?)>[];

  void updateUser(String ownerUid, List<String> providerIds) {
    user = _FixtureUser(ownerUid, providerIds);
    notifyListeners();
  }

  @override
  Future<ProviderLinkResult?> linkWithGoogle({String? expectedOwnerUid, ProviderLinkAuthorization? authorization}) =>
      _link('google.com', expectedOwnerUid, authorization: authorization);

  @override
  Future<ProviderLinkResult?> linkWithApple({String? expectedOwnerUid, ProviderLinkAuthorization? authorization}) =>
      _link('apple.com', expectedOwnerUid, authorization: authorization);

  Future<ProviderLinkResult?> _link(String providerId, String? expectedOwnerUid,
      {ProviderLinkAuthorization? authorization}) async {
    linkAttempts.add((providerId, expectedOwnerUid));
    return onLink!(providerId, authorization);
  }
}

class _FixtureUser implements User {
  _FixtureUser(this.uid, List<String> providerIds) : providerData = providerIds.map(_FixtureProvider.new).toList();

  @override
  final String uid;

  @override
  final bool isAnonymous = false;

  @override
  final List<UserInfo> providerData;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FixtureProvider implements UserInfo {
  const _FixtureProvider(this.providerId);

  @override
  final String providerId;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
