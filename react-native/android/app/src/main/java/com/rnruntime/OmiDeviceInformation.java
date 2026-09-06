package com.rnruntime;

import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.AbstractMap;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

final class OmiDeviceInformation {
  static final Map<UUID, String> fields;

  static {
    Map<UUID, String> values = new LinkedHashMap<>();
    String[][] pairs = {{"2a24", "model"}, {"2a26", "firmware"}, {"2a27", "hardware"}, {"2a29", "manufacturer"}, {"2a25", "serial"}};
    for (String[] pair : pairs) values.put(UUID.fromString("0000" + pair[0] + "-0000-1000-8000-00805f9b34fb"), pair[1]);
    fields = Collections.unmodifiableMap(values);
  }

  static Map.Entry<String, String> decode(UUID uuid, byte[] bytes) {
    String field = fields.get(uuid);
    if (field == null || bytes.length == 0 || bytes.length > 512) return null;
    String value;
    try {
      value = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
          .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
    } catch (CharacterCodingException error) {
      return null;
    }
    int start = 0;
    int end = value.length();
    while (start < end && Character.isWhitespace(value.charAt(start))) start++;
    while (end > start && Character.isWhitespace(value.charAt(end - 1))) end--;
    value = value.substring(start, end);
    if (value.isEmpty()) return null;
    for (int index = 0; index < value.length(); index++) if (Character.isISOControl(value.charAt(index))) return null;
    return new AbstractMap.SimpleImmutableEntry<>(field, value);
  }
}
