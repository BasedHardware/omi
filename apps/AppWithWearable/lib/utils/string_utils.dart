// string_utils.dart

String extractJson(String input) {
  int braceCount = 0;
  int startIndex = -1;
  int endIndex = -1;

  for (int i = 0; i < input.length; i++) {
    switch (input[i]) {
      case '{':
        braceCount++;
        startIndex = (startIndex == -1) ? i : startIndex;
        break;
      case '}':
        braceCount--;
        if (braceCount == 0 && startIndex != -1) {
          endIndex = i;
          break;
        }
        break;
      default:
        continue;
    }

    if (endIndex != -1) {
      break;
    }
  }

  if (startIndex != -1 && endIndex != -1) {
    return input.substring(startIndex, endIndex + 1);
  }
  return '';
}