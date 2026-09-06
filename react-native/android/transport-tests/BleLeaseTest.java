package com.rnruntime;

public final class BleLeaseTest {
  public static void main(String[] args) {
    assert OmiBleLease.recordingReady(true, true, true);
    assert !OmiBleLease.recordingReady(true, false, true);
    assert !OmiBleLease.recordingReady(true, true, false);
    assert !OmiBleLease.recordingReady(false, true, true);
    OmiBleLease.Reconnect reconnect = new OmiBleLease.Reconnect();
    assert reconnect.nextDelayMillis() == -1;
    reconnect.ready();
    assert reconnect.nextDelayMillis() == 1000;
    long retry = reconnect.token();
    assert reconnect.accepts(retry);
    assert reconnect.nextDelayMillis() == 2000;
    assert !reconnect.accepts(retry);
    assert reconnect.nextDelayMillis() == 4000;
    assert reconnect.nextDelayMillis() == -1;
    assert !reconnect.accepts(reconnect.token());
    reconnect.ready();
    assert reconnect.nextDelayMillis() == 1000;
    retry = reconnect.token();
    reconnect.cancel();
    assert !reconnect.accepts(retry);
    assert reconnect.nextDelayMillis() == -1;
    reconnect.ready();
    assert !reconnect.accepts(retry);
    OmiBleLease lease = new OmiBleLease();
    long first = lease.begin();
    Object firstGatt = new Object();
    Object nextGatt = new Object();
    assert lease.acceptsGatt(first, firstGatt, firstGatt);
    assert !lease.acceptsGatt(first, nextGatt, firstGatt);
    assert !lease.acceptsGatt(first, null, firstGatt);
    long operation = lease.operation();
    assert lease.accepts(first);
    assert lease.operationPending(first, operation);
    lease.operation();
    assert !lease.operationPending(first, operation);
    lease.retire();
    assert !lease.accepts(first);
    assert !lease.acceptsGatt(first, firstGatt, firstGatt);
    assert !lease.operationPending(first, operation);
    long second = lease.begin();
    long nextOperation = lease.operation();
    assert !lease.accepts(first);
    assert !lease.operationPending(first, nextOperation);
    assert lease.accepts(second);
    assert lease.operationPending(second, nextOperation);
    lease.retire();
    assert !lease.operationPending(second, nextOperation);
    System.out.println("BLE retired connection and operation timeout fencing passed");
  }
}
