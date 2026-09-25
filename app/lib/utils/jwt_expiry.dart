import 'dart:convert';

/// Reads `exp` out of a JWT, or null when the token cannot be read.
///
/// The token carries its own expiry, so a second copy of it kept beside the
/// token can only ever drift: a stored expiry that advances while the stored
/// token does not leaves the client certain a dead credential is fresh.
DateTime? jwtExpiry(String token) {
  final segments = token.split('.');
  if (segments.length < 2) return null;
  try {
    final payload = jsonDecode(utf8.decode(base64Url.decode(base64Url.normalize(segments[1]))));
    if (payload is! Map) return null;
    final exp = payload['exp'];
    if (exp is! int || exp <= 0) return null;
    return DateTime.fromMillisecondsSinceEpoch(exp * 1000, isUtc: true).toLocal();
  } catch (_) {
    return null;
  }
}
