package com.rnruntime;

final class OmiWearableSession {
  private long generation;
  private boolean active;
  synchronized long begin() { active = true; return ++generation; }
  synchronized boolean active() { return active; }
  synchronized boolean current(long ticket) { return active && ticket == generation; }
  synchronized boolean retire(long ticket) {
    if (!current(ticket)) return false;
    active = false;
    return true;
  }
}
