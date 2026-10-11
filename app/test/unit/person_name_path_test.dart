import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/users.dart';

void main() {
  String sentName(String name) =>
      Uri.parse('https://api.test/${personNamePath('person-1', name)}').queryParameters['value']!;

  test('a person name reaches the server unchanged', () {
    for (final name in ['Tom & Jerry', 'Dr. #1', 'A+B', 'Zoë 50%', 'x=y?']) {
      expect(sentName(name), name);
    }
  });

  test('the name stays in the value parameter', () {
    final uri = Uri.parse('https://api.test/${personNamePath('person-1', 'Tom & Jerry=1')}');
    expect(uri.path, '/v1/users/people/person-1/name');
    expect(uri.queryParameters.keys, ['value']);
  });
}
