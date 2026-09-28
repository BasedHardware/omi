#import "OmiAudioCapture.mm"
#include <cassert>
#include <cstdio>

int main(void) {
  @autoreleasepool {
    NSString *directory =
        [NSTemporaryDirectory() stringByAppendingPathComponent:@"omi-ambient-spool-test"];
    [NSFileManager.defaultManager removeItemAtPath:directory error:nil];

    // Packet framing: [seq u16 LE][fragment=0][opus bytes].
    NSData *opus = [@"opus-payload-bytes" dataUsingEncoding:NSUTF8StringEncoding];
    NSData *framed = OmiAmbientFramePacket(0x1234, opus);
    assert(framed.length == opus.length + 3);
    const uint8_t *bytes = (const uint8_t *)framed.bytes;
    assert(bytes[0] == 0x34 && bytes[1] == 0x12 && bytes[2] == 0);
    assert(memcmp(bytes + 3, opus.bytes, opus.length) == 0);
    NSData *wrapped = OmiAmbientFramePacket(0x10000, opus);
    const uint8_t *wrappedBytes = (const uint8_t *)wrapped.bytes;
    assert(wrappedBytes[0] == 0 && wrappedBytes[1] == 0); // sequence wraps u16

    // Spool roundtrip: write, list, batched reads, bounds, ack.
    NSMutableArray<NSData *> *packets = [NSMutableArray new];
    for (NSUInteger index = 0; index < 130; index += 1) {
      [packets addObject:OmiAmbientFramePacket(index, opus)];
    }
    NSError *error = nil;
    assert(OmiAmbientSpoolWrite(directory, 20, 1700000000000, packets, &error));
    NSArray<NSDictionary *> *listed = OmiAmbientSpoolList(directory);
    assert(listed.count == 1);
    NSDictionary *segment = listed[0];
    assert([segment[@"packets"] unsignedIntValue] == 130);
    assert([segment[@"codec"] unsignedIntValue] == 20);
    assert([segment[@"capturedAtMs"] longLongValue] == 1700000000000);
    assert([segment[@"bytes"] unsignedLongLongValue] > OmiAmbientHeaderLength);
    NSString *identifier = segment[@"id"];

    NSDictionary *first = OmiAmbientSpoolRead(directory, identifier, 0, 128, &error);
    assert(first != nil);
    assert([first[@"total"] unsignedIntValue] == 130);
    assert([first[@"packets"] count] == 128);
    assert([first[@"offset"] unsignedIntValue] == 0);
    NSData *firstPacket =
        [[NSData alloc] initWithBase64EncodedString:first[@"packets"][0]
                                            options:0];
    assert(firstPacket.length == opus.length + 3);

    NSDictionary *tail = OmiAmbientSpoolRead(directory, identifier, 128, 128, &error);
    assert(tail != nil);
    assert([tail[@"packets"] count] == 2);
    assert([tail[@"offset"] unsignedIntValue] == 128);

    // Past-end and corrupt/traversal identifiers must fail closed.
    assert(OmiAmbientSpoolRead(directory, identifier, 130, 128, &error) == nil);
    assert(OmiAmbientSpoolRead(directory, @"../../etc/passwd", 0, 128, &error) == nil);
    assert(OmiAmbientSpoolRead(directory, @"seg-evil", 0, 128, &error) == nil);
    assert(OmiAmbientSpoolRemove(directory, @"seg-evil/../x.omiseg", &error) == NO);
    assert(OmiAmbientSpoolRemove(directory, @"seg-plain", &error) == NO);

    // Oldest-first ordering across segments.
    assert(OmiAmbientSpoolWrite(directory, 20, 1700000001000, @[OmiAmbientFramePacket(0, opus)], &error));
    listed = OmiAmbientSpoolList(directory);
    assert(listed.count == 2);
    assert([listed[0][@"capturedAtMs"] longLongValue] <=
           [listed[1][@"capturedAtMs"] longLongValue]);

    assert(OmiAmbientSpoolRemove(directory, identifier, &error));
    listed = OmiAmbientSpoolList(directory);
    assert(listed.count == 1);
    assert(OmiAmbientSpoolRemove(directory, listed[0][@"id"], &error));
    assert(OmiAmbientSpoolList(directory).count == 0);
    OmiAmbientSpoolPrune(directory); // empty prune must not crash
    [NSFileManager.defaultManager removeItemAtPath:directory error:nil];
    printf("Omi ambient audio framing, spool roundtrip, bounds and traversal guards passed\n");
  }
  return 0;
}
