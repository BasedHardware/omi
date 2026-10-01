#import <Foundation/Foundation.h>

typedef NSDictionary *_Nullable(^OmiAmbientIdentity)(void);
typedef void (^OmiAmbientPermissionHandler)(NSString *state);

/**
 * Always-on desktop microphone capture for the v5 wire: 16 kHz mono Opus
 * packets framed exactly like wearable recordings ([seq u16 LE][fragment u8]
 * [opus bytes], fragment 0 = frame start), spooled to durable per-segment
 * files that the JS uploader drains through the device-session endpoints.
 */
@interface OmiAudioCapture : NSObject
- (instancetype)initWithIdentity:(OmiAmbientIdentity)identity root:(NSURL *)root;
- (void)requestMicrophonePermission:(OmiAmbientPermissionHandler)completion;
- (BOOL)startCapture:(NSError **)error;
- (void)stopCapture;
- (NSDictionary *)status;
/** Closed segments on disk, oldest first, that still need upload. */
- (NSArray<NSDictionary *> *)pendingSegments;
/** Up to `limit` framed packets from `offset`: {codec, capturedAtMs, packets, total, offset}. */
- (nullable NSDictionary *)segmentPackets:(NSString *)identifier
                                   offset:(NSUInteger)offset
                                    limit:(NSUInteger)limit
                                    error:(NSError **)error;
/** Removes a closed segment after its upload is durable. */
- (BOOL)acknowledgeSegment:(NSString *)identifier error:(NSError **)error;
- (void)invalidate;
@end
