import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/connectivity_service.dart';

void main() {
  test('ordinary builds probe general internet without spending the API edge budget', () {
    final options = connectivityProbeOptions(physicalQualification: false, apiBaseUrl: 'https://api.omi.me/');
    expect(options, hasLength(1));
    expect(options.single.uri, Uri.parse('https://one.one.one.one'));
    expect(options.single.timeout, const Duration(seconds: 3));
  });
  test('physical qualification keeps the selected local backend fixture probe', () {
    final options = connectivityProbeOptions(physicalQualification: true, apiBaseUrl: 'http://127.0.0.1:8080/');
    expect(options.single.uri, Uri.parse('http://127.0.0.1:8080/v1/health'));
  });
}
