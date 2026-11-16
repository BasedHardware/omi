# LittleFS multi-file read liveness

Evidence inspected 2026-11-14 UTC for Q12-I / PR #25331. This applies to the
multi-file protocol in released firmware tags 3.0.17–3.0.19, not the later ring
protocol in current main. No firmware change is part of this app fix.

| Tag | Commit |
| --- | --- |
| Omi_CV1_v3.0.17 | 6cc7adcbd675ff8279484a14ac8c4fc923dd979e |
| Omi_CV1_v3.0.18 | c3bb367d612f9bcfd909c2f0231d292a33a68214 |
| Omi_CV1_v3.0.19 | b3955bbdc1eb632613efe301d7d4a0fe642b3def |

Read with managed Git, for example:

```sh
git show Omi_CV1_v3.0.19:omi/firmware/omi/src/lib/core/storage.c
git show Omi_CV1_v3.0.19:omi/firmware/omi/src/sd_card.c
```

In all three tags, `read_audio_data` permits up to 500ms to queue an SD request,
then 15000ms waiting for its worker: **15.5s before BLE delivery**. These waits
are at `sd_card.c:1700,1707` in 3.0.17 and `:1885,1892` in 3.0.18/.19.

`storage.c` reads a batch before notifying each timestamp-prefixed DATA chunk.
In .19 the batch read is at line 550 and notify/retry loop at lines 569–584.
On `-ENOMEM`, it yields and retries without a deadline. On `-EAGAIN`, it
returns and the active worker yields/retries. The connected 1ms idle poll is
used only when no data remains; it does not bound a transfer's notification gap.
The same retry structure is present in .17 (`:498–531`) and .18 (`:498–531`).

There is **no finite maximum legitimate inter-DATA gap** in this source.
`heartbeat_count` only saves the offset locally; it does not emit a phone
progress signal. A single-byte ACK confirms a command, not bytes read. The
four-byte DATA prefix is the recording timestamp, not a monotonic progress
counter. Therefore ACKs/status chatter cannot safely renew audio liveness.

The app uses conservative **60-second deadlines for first parsed audio DATA
and subsequent audio idle**, allowing almost four SD read windows and BLE
delivery margin. The 10-minute overall ceiling remains. The first-DATA window
starts before the read command; ACKs cannot cancel or renew it. Sixty seconds
is an app recovery policy, not a firmware-guaranteed upper bound. A longer healthy
gap can still require retry; incomplete reads retain the device record and
durably save parsed frames without advancing an unread head.

`OMI_STORAGE_AUDIO_LIVENESS_OFF=true` restores any-packet first-data detection
with the original five-second first-packet deadline and disables the DATA idle
deadline. It **does not** restore silent successful
returns for incomplete transfers, remove cleanup or weaken durability/delete
proof. Bulk and single-recording incomplete transfers still report failure.

Guard: `app/test/unit/legacy_storage_limitless_seam_test.dart` checks a healthy
20-second delay before the first DATA, a healthy 45-second DATA gap, ACK-only
failure at 60 seconds, idle expiry, timer cleanup and custody.
