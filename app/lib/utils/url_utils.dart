/// Adds or replaces the `uid` query parameter without corrupting existing
/// query parameters or URL fragments.
String withUidQueryParameter(String rawUrl, String uid) {
  final uri = Uri.tryParse(rawUrl);
  if (uri == null) return rawUrl;
  final query = <String, String>{...uri.queryParameters, 'uid': uid};
  return uri.replace(queryParameters: query).toString();
}
