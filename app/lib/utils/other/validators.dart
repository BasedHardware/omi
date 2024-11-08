bool isValidUrl(String url) {
  const urlPattern = r'^(https?:\/\/)?([a-zA-Z0-9.-]+(:[a-zA-Z0-9.&%$-]+)*@)?'
      r'((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
      r'(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)|'
      r'([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,63}(:[0-9]+)?(\/.*)?$';
  return RegExp(urlPattern).hasMatch(url);
}

bool isValidWebSocketUrl(String url) {
  const webSocketPattern = r'^(wss?:\/\/)?([a-zA-Z0-9.-]+(:[a-zA-Z0-9.&%$-]+)*@)?'
      r'((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
      r'(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)|'
      r'([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,63}(:[0-9]+)?(\/.*)?$';
  return RegExp(webSocketPattern).hasMatch(url);
}

bool isValidEmail(String email) {
  const emailPattern = r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$';
  return RegExp(emailPattern).hasMatch(email);
}
