package com.rnruntime;

final class OmiDeviceControls {
  static final class FindPattern {
    static final int LEVEL = 3;
    static final int DELAY_MS = 750;
    private long generation;
    private int sent;
    private boolean active;
    private boolean awaiting;
    long begin() { cancel(); active = true; return generation; }
    void cancel() { generation++; active = false; awaiting = false; sent = 0; }
    boolean send(long ticket) {
      if (ticket != generation || !active || awaiting || sent >= 3) return false;
      sent++; awaiting = true; return true;
    }
    boolean acknowledge(long ticket) {
      if (ticket != generation || !active || !awaiting) return false;
      awaiting = false; return true;
    }
    boolean complete() { return active && sent == 3 && !awaiting; }
  }
  static long[] storage(byte[] bytes) {
    if (bytes.length != 16) return null;
    long[] values = new long[4];
    for (int field = 0; field < 4; field++) for (int index = 0; index < 4; index++)
      values[field] |= (long) (bytes[field * 4 + index] & 255) << (index * 8);
    return values[3] <= 1 && values[0] + values[2] > 0 ? values : null;
  }
  static boolean storageSupported(Long features) { return features != null && (features & (1L << 6)) != 0; }
  static Long features(byte[] bytes) {
    if (bytes.length != 4) return null;
    long value = 0;
    for (int index = 0; index < 4; index++) value |= (long) (bytes[index] & 255) << (index * 8);
    return value;
  }
  static int maximum(String setting) {
    return "ledBrightness".equals(setting) ? 100 : "microphoneGain".equals(setting) ? 8 : -1;
  }
  static boolean supports(Long features, String setting) {
    if (features == null) return false;
    int bit = "ledBrightness".equals(setting) ? 7 : "microphoneGain".equals(setting) ? 8 : -1;
    return bit >= 0 && (features & (1L << bit)) != 0;
  }
  static Integer value(String setting, byte[] bytes) {
    if (bytes.length != 1) return null;
    int value = bytes[0] & 255;
    return value <= maximum(setting) ? value : null;
  }
  static boolean validWrite(Long features, String setting, double value) {
    return supports(features, setting) && Double.isFinite(value) && value == Math.floor(value) && value >= 0 && value <= maximum(setting);
  }
}
