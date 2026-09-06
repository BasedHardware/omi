package com.rnruntime;

final class OmiBleLease {
  static boolean recordingReady(boolean connected, boolean notifying, boolean hasCodec) {
    return connected && notifying && hasCodec;
  }
  private long generation;
  private long operation;
  private boolean active;
  synchronized long begin() { active = true; operation++; return ++generation; }
  synchronized void retire() { active = false; generation++; operation++; }
  synchronized boolean accepts(long token) { return active && generation == token; }
  synchronized boolean acceptsGatt(long token, Object current, Object callback) { return current != null && current == callback && accepts(token); }
  synchronized long operation() { return ++operation; }
  synchronized boolean operationPending(long token, long ticket) { return accepts(token) && operation == ticket; }
  static final class Reconnect {
    private long generation;
    private boolean armed;
    private int attempts;
    void ready() { armed = true; attempts = 0; generation++; }
    void cancel() { armed = false; attempts = 0; generation++; }
    long nextDelayMillis() {
      if (!armed || attempts == 3) { cancel(); return -1; }
      generation++;
      return 1000L << attempts++;
    }
    long token() { return generation; }
    boolean accepts(long token) { return armed && generation == token; }
    int attempts() { return attempts; }
  }
}
