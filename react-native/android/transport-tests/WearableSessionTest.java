package com.rnruntime;

public final class WearableSessionTest {
  public static void main(String[] args) {
    OmiWearableSession session = new OmiWearableSession();
    assert !session.active();
    long first = session.begin();
    assert session.current(first);
    assert session.active();
    assert session.retire(first);
    assert !session.current(first);
    assert !session.active();
    long replacement = session.begin();
    assert !session.retire(first);
    assert !session.current(first);
    assert session.current(replacement);
    assert session.active();
    assert session.retire(replacement);
    assert !session.retire(replacement);
    assert !session.active();
    long third = session.begin();
    long fourth = session.begin();
    assert !session.retire(third);
    assert session.current(fourth);
    assert session.retire(fourth);
    System.out.println("Wearable service owner, cancellation and stale-action checks passed");
  }
}
