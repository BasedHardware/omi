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
}
