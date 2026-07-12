import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/sockets/pure_socket.dart';

void main() {
  test('unavailable auth blocks a socket before opening the network', () async {
    final socket = PureSocket(
      'wss://example.invalid',
      headersProvider: () async {
        throw AuthTokenUnavailableException(const AuthTokenTransientFailure(failureClass: 'offline'));
      },
    );

    expect(await socket.connect(), isFalse);
    expect(socket.status, PureSocketStatus.notConnected);
  });
}
