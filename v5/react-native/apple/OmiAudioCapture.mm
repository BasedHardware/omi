#import "OmiAudioCapture.h"
#import <AVFoundation/AVFoundation.h>
#import <AppKit/AppKit.h>
#import <AudioToolbox/AudioToolbox.h>
#import <fcntl.h>
#import <unistd.h>
#import <sys/stat.h>

static const uint8_t OmiAmbientCodec = 20; // Opus, 16 kHz mono, on the v5 wire
static NSString *const OmiAmbientSegmentExtension = @"omiseg";
static NSString *const OmiAmbientSegmentPrefix = @"seg-";
static const uint8_t OmiAmbientHeaderMagic[7] = {'O', 'M', 'I', 'A', 'M', 'B', '1'};
static const NSUInteger OmiAmbientHeaderLength = 8 + 8 + 4; // magic+codec, capturedAtMs, packetCount
static const long long OmiAmbientQuotaBytes = 512LL * 1024 * 1024;
static const NSTimeInterval OmiAmbientSegmentSeconds = 300.0;
static const long long OmiAmbientSegmentBytes = 6LL * 1024 * 1024;
static const NSUInteger OmiAmbientSegmentPackets = 64000;
static const double OmiAmbientSampleRate = 16000.0;
static const NSInteger OmiAmbientChannels = 1;
static const AVAudioFrameCount OmiAmbientTapBufferFrames = 8192;
static const NSUInteger OmiAmbientMaxOpusPacket = 2048;
static const NSUInteger OmiAmbientMaxEncodePackets = 8;

static NSError *OmiAmbientError(NSString *code) {
  return [NSError errorWithDomain:code code:1 userInfo:nil];
}
static BOOL OmiAmbientIdentityValid(NSDictionary *identity) {
  NSString *uid = identity[@"uid"], *login = identity[@"login"];
  if (![uid isKindOfClass:NSString.class] || ![login isKindOfClass:NSString.class] || login.length == 0 || uid.length > 128) return NO;
  return [uid rangeOfString:@"^[A-Za-z0-9_-]+$" options:NSRegularExpressionSearch].location != NSNotFound;
}
static NSString *OmiAmbientSegmentDirectory(NSURL *root, NSString *uid) {
  return [[[[root URLByAppendingPathComponent:@"users"] URLByAppendingPathComponent:uid] URLByAppendingPathComponent:@"ambient"] path];
}
static BOOL OmiAmbientEnsureDirectory(NSString *path) {
  NSFileManager *files = NSFileManager.defaultManager;
  NSDictionary *attributes = [files attributesOfItemAtPath:path error:nil];
  if (attributes != nil) return [attributes[NSFileType] isEqual:NSFileTypeDirectory];
  return [files createDirectoryAtPath:path withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0700} error:nil];
}
static BOOL OmiAmbientIdentifierValid(NSString *identifier) {
  if (identifier.length < 8 || identifier.length > 128) return NO;
  if (![identifier hasPrefix:OmiAmbientSegmentPrefix] ||
      ![identifier hasSuffix:[@"." stringByAppendingString:OmiAmbientSegmentExtension]]) {
    return NO;
  }
  // No path separators can appear: the name is a flat, generated filename.
  static NSCharacterSet *allowed = nil;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ allowed = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyz0123456789-."]; });
  return [identifier stringByTrimmingCharactersInSet:allowed].length == 0;
}

#pragma mark - Segment spool (durable files, oldest-first drain)

static void OmiAmbientPut32(uint8_t *cursor, uint32_t value) {
  cursor[0] = (uint8_t)(value & 0xff);
  cursor[1] = (uint8_t)((value >> 8) & 0xff);
  cursor[2] = (uint8_t)((value >> 16) & 0xff);
  cursor[3] = (uint8_t)((value >> 24) & 0xff);
}
static void OmiAmbientPut64(uint8_t *cursor, uint64_t value) {
  OmiAmbientPut32(cursor, (uint32_t)(value & 0xffffffff));
  OmiAmbientPut32(cursor + 4, (uint32_t)(value >> 32));
}
static uint32_t OmiAmbientGet32(const uint8_t *cursor) {
  return (uint32_t)cursor[0] | ((uint32_t)cursor[1] << 8) | ((uint32_t)cursor[2] << 16) | ((uint32_t)cursor[3] << 24);
}
static uint64_t OmiAmbientGet64(const uint8_t *cursor) {
  return (uint64_t)OmiAmbientGet32(cursor) | ((uint64_t)OmiAmbientGet32(cursor + 4) << 32);
}

/** One framed packet per Opus frame: [seq u16 LE][fragment=0][opus bytes]. */
static NSData *OmiAmbientFramePacket(NSUInteger sequence, NSData *opus) {
  NSMutableData *framed = [NSMutableData dataWithLength:3 + opus.length];
  uint8_t *bytes = (uint8_t *)framed.mutableBytes;
  bytes[0] = (uint8_t)(sequence & 0xff);
  bytes[1] = (uint8_t)((sequence >> 8) & 0xff);
  bytes[2] = 0;
  memcpy(bytes + 3, opus.bytes, opus.length);
  return framed;
}

static BOOL OmiAmbientSpoolWrite(NSString *directory, uint8_t codec, int64_t capturedAtMs, NSArray<NSData *> *packets, NSError **error) {
  if (packets.count == 0 || packets.count > OmiAmbientSegmentPackets) {
    if (error) *error = OmiAmbientError(@"OMI_CAPTURE_STORAGE");
    return NO;
  }
  if (!OmiAmbientEnsureDirectory(directory)) {
    if (error) *error = OmiAmbientError(@"OMI_CAPTURE_STORAGE");
    return NO;
  }
  long long payload = 0;
  for (NSData *packet in packets) payload += packet.length;
  NSMutableData *blob = [NSMutableData dataWithCapacity:OmiAmbientHeaderLength + payload + packets.count * 4];
  uint8_t header[OmiAmbientHeaderLength];
  memcpy(header, OmiAmbientHeaderMagic, sizeof(OmiAmbientHeaderMagic));
  header[7] = codec;
  OmiAmbientPut64(header + 8, (uint64_t)capturedAtMs);
  OmiAmbientPut32(header + 16, (uint32_t)packets.count);
  [blob appendBytes:header length:OmiAmbientHeaderLength];
  for (NSData *packet in packets) {
    uint8_t length[4];
    OmiAmbientPut32(length, (uint32_t)packet.length);
    [blob appendBytes:length length:4];
    [blob appendData:packet];
  }
  NSString *identifier = [NSString stringWithFormat:@"%@%lld-%@.%@", OmiAmbientSegmentPrefix, (long long)capturedAtMs, NSUUID.UUID.UUIDString.lowercaseString, OmiAmbientSegmentExtension];
  NSURL *final = [[NSURL fileURLWithPath:directory] URLByAppendingPathComponent:identifier];
  NSURL *temporary = [[NSURL fileURLWithPath:directory] URLByAppendingPathComponent:[@"." stringByAppendingString:identifier]];
  NSData *written = blob;
  if (![written writeToURL:temporary options:0 error:error]) {
    [NSFileManager.defaultManager removeItemAtURL:temporary error:nil];
    if (error) *error = OmiAmbientError(@"OMI_CAPTURE_STORAGE");
    return NO;
  }
  int fd = open(temporary.fileSystemRepresentation, O_RDONLY);
  if (fd >= 0) {
    fcntl(fd, F_FULLFSYNC);
    close(fd);
  }
  if (![NSFileManager.defaultManager moveItemAtURL:temporary toURL:final error:error]) {
    [NSFileManager.defaultManager removeItemAtURL:temporary error:nil];
    if (error) *error = OmiAmbientError(@"OMI_CAPTURE_STORAGE");
    return NO;
  }
  return YES;
}

static NSArray<NSDictionary *> *OmiAmbientSpoolList(NSString *directory) {
  NSFileManager *files = NSFileManager.defaultManager;
  NSArray<NSURL *> *contents = [files contentsOfDirectoryAtURL:[NSURL fileURLWithPath:directory]
                                   includingPropertiesForKeys:@[NSURLFileSizeKey, NSURLIsSymbolicLinkKey]
                                                      options:0
                                                        error:nil];
  if (contents == nil) return @[];
  NSMutableArray<NSDictionary *> *segments = [NSMutableArray new];
  for (NSURL *url in contents) {
    NSString *name = url.lastPathComponent;
    if (![name hasPrefix:OmiAmbientSegmentPrefix] || ![url.pathExtension.lowercaseString isEqual:OmiAmbientSegmentExtension]) continue;
    NSNumber *link = nil, *bytes = nil;
    [url getResourceValue:&link forKey:NSURLIsSymbolicLinkKey error:nil];
    if (link.boolValue) continue;
    [url getResourceValue:&bytes forKey:NSURLFileSizeKey error:nil];
    // Header: magic, codec, capturedAtMs, packetCount.
    NSData *header = nil;
    NSFileHandle *handle = [NSFileHandle fileHandleForReadingFromURL:url error:nil];
    if (handle != nil) {
      @try {
        header = [handle readDataUpToLength:OmiAmbientHeaderLength error:nil];
      } @finally {
        [handle closeAndReturnError:nil];
      }
    }
    if (header.length != OmiAmbientHeaderLength) continue;
    const uint8_t *raw = (const uint8_t *)header.bytes;
    if (memcmp(raw, OmiAmbientHeaderMagic, sizeof(OmiAmbientHeaderMagic)) != 0) continue;
    [segments addObject:@{
      @"id": name,
      @"codec": @(raw[7]),
      @"capturedAtMs": @((long long)OmiAmbientGet64(raw + 8)),
      @"packets": @((NSUInteger)OmiAmbientGet32(raw + 16)),
      @"bytes": bytes ?: @0,
    }];
  }
  [segments sortUsingComparator:^NSComparisonResult(NSDictionary *left, NSDictionary *right) {
    return [left[@"id"] compare:right[@"id"] options:NSNumericSearch];
  }];
  return segments;
}

static NSDictionary *OmiAmbientSpoolRead(NSString *directory, NSString *identifier, NSUInteger offset, NSUInteger limit, NSError **error) {
  if (!OmiAmbientIdentifierValid(identifier) || limit == 0 || limit > 128) {
    if (error) *error = OmiAmbientError(@"OMI_CAPTURE_REQUEST");
    return nil;
  }
  NSData *blob = [NSData dataWithContentsOfFile:[directory stringByAppendingPathComponent:identifier] options:0 error:error];
  if (blob.length < OmiAmbientHeaderLength) {
    if (error) *error = OmiAmbientError(@"OMI_CAPTURE_SEGMENT_MISSING");
    return nil;
  }
  const uint8_t *raw = (const uint8_t *)blob.bytes;
  if (memcmp(raw, OmiAmbientHeaderMagic, sizeof(OmiAmbientHeaderMagic)) != 0) {
    if (error) *error = OmiAmbientError(@"OMI_CAPTURE_SEGMENT_CORRUPT");
    return nil;
  }
  NSUInteger total = (NSUInteger)OmiAmbientGet32(raw + 16);
  NSUInteger cursor = OmiAmbientHeaderLength;
  NSMutableArray<NSString *> *packets = [NSMutableArray new];
  for (NSUInteger index = 0; index < total; index += 1) {
    if (cursor + 4 > blob.length) {
      if (error) *error = OmiAmbientError(@"OMI_CAPTURE_SEGMENT_CORRUPT");
      return nil;
    }
    NSUInteger length = (NSUInteger)OmiAmbientGet32(raw + cursor);
    cursor += 4;
    if (length == 0 || cursor + length > blob.length) {
      if (error) *error = OmiAmbientError(@"OMI_CAPTURE_SEGMENT_CORRUPT");
      return nil;
    }
    if (index >= offset && packets.count < limit) {
      [packets addObject:[[NSData dataWithBytes:raw + cursor length:length] base64EncodedStringWithOptions:0]];
    }
    cursor += length;
  }
  if (offset >= total || packets.count == 0) {
    if (error) *error = OmiAmbientError(@"OMI_CAPTURE_SEGMENT_RANGE");
    return nil;
  }
  return @{
    @"codec": @(raw[7]),
    @"capturedAtMs": @((long long)OmiAmbientGet64(raw + 8)),
    @"packets": packets,
    @"total": @(total),
    @"offset": @(offset),
  };
}

static BOOL OmiAmbientSpoolRemove(NSString *directory, NSString *identifier, NSError **error) {
  if (!OmiAmbientIdentifierValid(identifier)) {
    if (error) *error = OmiAmbientError(@"OMI_CAPTURE_REQUEST");
    return NO;
  }
  if (![NSFileManager.defaultManager removeItemAtPath:[directory stringByAppendingPathComponent:identifier] error:error]) {
    if (error) *error = OmiAmbientError(@"OMI_CAPTURE_SEGMENT_MISSING");
    return NO;
  }
  return YES;
}

static void OmiAmbientSpoolPrune(NSString *directory) {
  NSArray<NSDictionary *> *segments = OmiAmbientSpoolList(directory);
  unsigned long long total = 0;
  for (NSDictionary *segment in segments) total += [segment[@"bytes"] unsignedLongLongValue];
  for (NSDictionary *segment in segments) {
    if (total <= (unsigned long long)OmiAmbientQuotaBytes) break;
    if ([NSFileManager.defaultManager removeItemAtPath:[directory stringByAppendingPathComponent:segment[@"id"]] error:nil]) {
      total -= [segment[@"bytes"] unsignedLongLongValue];
    }
  }
}

#pragma mark - Opus encode feed

typedef struct {
  const Float32 *cursor;
  NSUInteger remaining;
} OmiAmbientEncodeFeed;

static OSStatus OmiAmbientInputProc(AudioConverterRef converter,
                                    UInt32 *ioPackets,
                                    AudioBufferList *ioData,
                                    AudioStreamPacketDescription **packetDescription,
                                    void *userInfo) {
  (void)converter;
  if (packetDescription != NULL) *packetDescription = NULL;
  OmiAmbientEncodeFeed *feed = (OmiAmbientEncodeFeed *)userInfo;
  UInt32 wanted = *ioPackets; // linear PCM: one frame per packet
  UInt32 take = (UInt32)MIN((NSUInteger)wanted, feed->remaining);
  if (take == 0) {
    *ioPackets = 0;
    return noErr;
  }
  ioData->mNumberBuffers = 1;
  ioData->mBuffers[0].mData = (void *)feed->cursor;
  ioData->mBuffers[0].mDataByteSize = take * (UInt32)sizeof(Float32);
  feed->cursor += take;
  feed->remaining -= take;
  *ioPackets = take;
  return noErr;
}

#pragma mark - Capture

@interface OmiAudioCapture ()
@property(nonatomic, copy) OmiAmbientIdentity identity;
@property(nonatomic, strong) NSURL *root;
@property(nonatomic, strong) dispatch_queue_t ioQueue;
@property(nonatomic, strong) NSMutableArray *observers;
@property(nonatomic, strong) AVAudioEngine *engine;
@property(nonatomic, strong) NSDate *startedAt;
@property(nonatomic, copy) NSString *uid;
@property(nonatomic) BOOL desired;
@property(nonatomic) BOOL disposed;
@property(nonatomic) BOOL locked;
@property(nonatomic) BOOL asleep;
@property(nonatomic) BOOL running;
@property(nonatomic) long long writtenBytes;
@property(nonatomic) NSUInteger chunks;
@property(nonatomic, copy) NSString *lastError;
// Opus encoder state, rebuilt with every engine session.
@property(nonatomic) AudioConverterRef encoder;
@property(nonatomic, strong) NSMutableArray<NSData *> *segmentPackets;
@property(nonatomic, strong) NSDate *segmentStart;
@property(nonatomic) long long segmentBytes;
@property(nonatomic) NSUInteger segmentSequence;
@end

@implementation OmiAudioCapture
- (instancetype)initWithIdentity:(OmiAmbientIdentity)identity root:(NSURL *)root {
  self = [super init];
  if (self) {
    _identity = [identity copy];
    _root = root;
    _ioQueue = dispatch_queue_create("omi.ambient.audio", DISPATCH_QUEUE_SERIAL);
    _observers = [NSMutableArray new];
    __weak OmiAudioCapture *weakSelf = self;
    for (NSString *name in @[NSWorkspaceWillSleepNotification, NSWorkspaceSessionDidResignActiveNotification, NSWorkspaceScreensDidSleepNotification]) {
      id observer = [NSWorkspace.sharedWorkspace.notificationCenter addObserverForName:name object:nil queue:nil usingBlock:^(NSNotification *note) {
        (void)note;
        OmiAudioCapture *owner = weakSelf;
        if (owner == nil) return;
        @synchronized(owner) { if ([name isEqual:NSWorkspaceSessionDidResignActiveNotification]) owner.locked = YES; else owner.asleep = YES; }
        [owner pauseEngine];
      }];
      [_observers addObject:observer];
    }
    id lock = [NSDistributedNotificationCenter.defaultCenter addObserverForName:@"com.apple.screenIsLocked" object:nil queue:nil usingBlock:^(NSNotification *note) {
      (void)note;
      OmiAudioCapture *owner = weakSelf;
      if (owner == nil) return;
      @synchronized(owner) { owner.locked = YES; }
      [owner pauseEngine];
    }];
    [_observers addObject:lock];
    for (NSString *name in @[NSWorkspaceDidWakeNotification, NSWorkspaceScreensDidWakeNotification, NSWorkspaceSessionDidBecomeActiveNotification]) {
      id observer = [NSWorkspace.sharedWorkspace.notificationCenter addObserverForName:name object:nil queue:nil usingBlock:^(NSNotification *note) {
        (void)note;
        OmiAudioCapture *owner = weakSelf;
        if (owner == nil) return;
        @synchronized(owner) { if ([name isEqual:NSWorkspaceSessionDidBecomeActiveNotification]) owner.locked = NO; else owner.asleep = NO; }
        [owner resumeEngine];
      }];
      [_observers addObject:observer];
    }
    id unlock = [NSDistributedNotificationCenter.defaultCenter addObserverForName:@"com.apple.screenIsUnlocked" object:nil queue:nil usingBlock:^(NSNotification *note) {
      (void)note;
      OmiAudioCapture *owner = weakSelf;
      if (owner == nil) return;
      @synchronized(owner) { owner.locked = NO; }
      [owner resumeEngine];
    }];
    [_observers addObject:unlock];
  }
  return self;
}
- (void)dealloc {
  for (id observer in self.observers) {
    [NSWorkspace.sharedWorkspace.notificationCenter removeObserver:observer];
    [NSDistributedNotificationCenter.defaultCenter removeObserver:observer];
  }
  if (_encoder != nil) AudioConverterDispose(_encoder);
}
- (AVAuthorizationStatus)microphoneStatus {
  return [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio];
}
- (void)requestMicrophonePermission:(OmiAmbientPermissionHandler)completion {
  @synchronized(self) {
    if (self.disposed) {
      dispatch_async(dispatch_get_main_queue(), ^{ completion(@"denied"); });
      return;
    }
  }
  AVAuthorizationStatus status = [self microphoneStatus];
  if (status != AVAuthorizationStatusNotDetermined) {
    dispatch_async(dispatch_get_main_queue(), ^{ completion(status == AVAuthorizationStatusAuthorized ? @"granted" : @"denied"); });
    return;
  }
  [AVCaptureDevice requestAccessForMediaType:AVMediaTypeAudio completionHandler:^(BOOL granted) {
    dispatch_async(dispatch_get_main_queue(), ^{ completion(granted ? @"granted" : @"denied"); });
  }];
}
- (BOOL)startCapture:(NSError **)error {
  @synchronized(self) {
    NSDictionary *owner = self.identity();
    if (self.disposed || !OmiAmbientIdentityValid(owner)) { if (error) *error = OmiAmbientError(@"OMI_CAPTURE_UNAUTHORIZED"); return NO; }
    if (self.microphoneStatus != AVAuthorizationStatusAuthorized) { if (error) *error = OmiAmbientError(@"OMI_CAPTURE_PERMISSION"); return NO; }
    self.desired = YES;
    self.uid = owner[@"uid"];
    self.lastError = nil;
  }
  return [self resumeEngine];
}
- (void)stopCapture {
  @synchronized(self) { self.desired = NO; }
  [self pauseEngine];
}
- (void)invalidate {
  @synchronized(self) { self.disposed = YES; self.desired = NO; }
  [self pauseEngine];
}
- (void)pauseEngine {
  AVAudioEngine *engine = nil;
  @synchronized(self) {
    if (!self.running) return;
    self.running = NO;
    self.startedAt = nil;
    [self closeActiveSegment];
    engine = self.engine;
    self.engine = nil;
    if (self.encoder != nil) {
      AudioConverterDispose(self.encoder);
      self.encoder = nil;
    }
  }
  // Tap removal happens outside the lock so an in-flight tap block waiting
  // on the same lock cannot deadlock with removeTapOnBus joining it.
  if (engine != nil) {
    @try { [engine.inputNode removeTapOnBus:0]; } @catch (NSException *failure) { (void)failure; }
    [engine stop];
  }
}
- (BOOL)resumeEngine {
  @synchronized(self) {
    if (self.disposed || self.running || !self.desired || self.locked || self.asleep) return YES;
    NSDictionary *owner = self.identity();
    if (!OmiAmbientIdentityValid(owner) || self.uid == nil || ![self.uid isEqual:owner[@"uid"]] || self.microphoneStatus != AVAuthorizationStatusAuthorized) return YES;
    AVAudioEngine *engine = [AVAudioEngine new];
    AVAudioFormat *inputFormat = [engine.inputNode outputFormatForBus:0];
    AVAudioFormat *targetFormat = [[AVAudioFormat alloc] initStandardFormatWithSampleRate:OmiAmbientSampleRate channels:OmiAmbientChannels];
    if (inputFormat == nil || targetFormat == nil || inputFormat.sampleRate < OmiAmbientSampleRate || inputFormat.channelCount < 1) {
      [engine stop];
      self.desired = NO;
      self.lastError = @"OMI_CAPTURE_UNAVAILABLE";
      return NO;
    }
    AVAudioConverter *converter = [[AVAudioConverter alloc] initFromFormat:inputFormat toFormat:targetFormat];
    if (converter == nil) {
      self.desired = NO;
      self.lastError = @"OMI_CAPTURE_UNAVAILABLE";
      return NO;
    }
    // Opus encoder: 16 kHz mono Float32 in, framed Opus packets out.
    AudioStreamBasicDescription pcm = {0};
    pcm.mSampleRate = OmiAmbientSampleRate;
    pcm.mFormatID = kAudioFormatLinearPCM;
    pcm.mFormatFlags = kAudioFormatFlagIsFloat | kAudioFormatFlagIsPacked;
    pcm.mFramesPerPacket = 1;
    pcm.mBytesPerFrame = (UInt32)sizeof(Float32);
    pcm.mBytesPerPacket = pcm.mBytesPerFrame;
    pcm.mChannelsPerFrame = (UInt32)OmiAmbientChannels;
    AudioStreamBasicDescription opus = {0};
    opus.mSampleRate = OmiAmbientSampleRate;
    opus.mFormatID = kAudioFormatOpus;
    opus.mChannelsPerFrame = (UInt32)OmiAmbientChannels;
    AudioConverterRef encoder = nil;
    if (AudioConverterNew(&pcm, &opus, &encoder) != noErr || encoder == nil) {
      self.desired = NO;
      self.lastError = @"OMI_CAPTURE_UNAVAILABLE";
      return NO;
    }
    __weak OmiAudioCapture *weakSelf = self;
    [engine.inputNode installTapOnBus:0 bufferSize:OmiAmbientTapBufferFrames format:inputFormat block:^(AVAudioPCMBuffer *buffer, AVAudioTime *when) {
      (void)when;
      OmiAudioCapture *owner = weakSelf;
      if (owner == nil) return;
      [owner writeSamples:buffer converter:converter encoder:encoder];
    }];
    [engine prepare];
    NSError *failure = nil;
    if (![engine startAndReturnError:&failure]) {
      (void)failure;
      AudioConverterDispose(encoder);
      @try { [engine.inputNode removeTapOnBus:0]; } @catch (NSException *stopFailure) { (void)stopFailure; }
      self.desired = NO;
      self.lastError = @"OMI_CAPTURE_UNAVAILABLE";
      return NO;
    }
    self.encoder = encoder;
    self.engine = engine;
    self.running = YES;
    self.startedAt = NSDate.date;
    return YES;
  }
}
- (void)writeSamples:(AVAudioPCMBuffer *)buffer converter:(AVAudioConverter *)converter encoder:(AudioConverterRef)encoder {
  @synchronized(self) {
    if (!self.running) return;
    NSDate *now = NSDate.date;
    if (self.segmentPackets == nil) {
      self.segmentPackets = [NSMutableArray new];
      self.segmentStart = now;
      self.segmentSequence = 0;
      self.segmentBytes = 0;
    } else if (self.segmentStart != nil &&
               ([now timeIntervalSinceDate:self.segmentStart] >= OmiAmbientSegmentSeconds ||
                self.segmentBytes >= OmiAmbientSegmentBytes ||
                self.segmentPackets.count >= OmiAmbientSegmentPackets)) {
      [self closeActiveSegment];
      self.segmentPackets = [NSMutableArray new];
      self.segmentStart = now;
      self.segmentSequence = 0;
      self.segmentBytes = 0;
    }
    // Stage 1: mic format -> 16 kHz mono Float32.
    NSError *failure = nil;
    AVAudioFrameCount capacity = (AVAudioFrameCount)ceil(buffer.frameLength * OmiAmbientSampleRate / converter.inputFormat.sampleRate) + 16;
    AVAudioPCMBuffer *output = [[AVAudioPCMBuffer alloc] initWithPCMFormat:converter.outputFormat frameCapacity:capacity];
    if (output == nil) return;
    __block BOOL consumed = NO;
    AVAudioConverterOutputStatus status = AVAudioConverterOutputStatus_HaveData;
    while (status == AVAudioConverterOutputStatus_HaveData) {
      output.frameLength = 0;
      status = [converter convertToBuffer:output error:&failure withInputFromBlock:^AVAudioBuffer *_Nullable(AVAudioPacketCount inNumberOfPackets, AVAudioConverterInputStatus *inStatus) {
        if (consumed) { *inStatus = AVAudioConverterInputStatus_NoDataNow; return nil; }
        consumed = YES;
        return buffer;
      }];
      if (output.frameLength == 0) continue;
      // Stage 2: Float32 -> Opus packets.
      OmiAmbientEncodeFeed feed = {.cursor = (const Float32 *)output.floatChannelData[0], .remaining = output.frameLength};
      while (feed.remaining > 0) {
        uint8_t storage[OmiAmbientMaxOpusPacket * OmiAmbientMaxEncodePackets];
        AudioBufferList out = {0};
        out.mNumberBuffers = 1;
        out.mBuffers[0].mData = storage;
        out.mBuffers[0].mDataByteSize = (UInt32)sizeof(storage);
        AudioStreamPacketDescription descriptions[OmiAmbientMaxEncodePackets];
        UInt32 packets = OmiAmbientMaxEncodePackets;
        OSStatus converted = AudioConverterFillComplexBuffer(encoder, OmiAmbientInputProc, &feed, &packets, &out, descriptions);
        if (converted != noErr) {
          self.lastError = @"OMI_CAPTURE_UNAVAILABLE";
          return;
        }
        for (UInt32 index = 0; index < packets; index += 1) {
          // mStartOffset -1 (contiguous) only happens for a single packet.
          NSInteger start = descriptions[index].mStartOffset;
          if (start < 0) start = packets == 1 ? 0 : -1;
          NSInteger length = descriptions[index].mDataByteSize;
          if (start < 0 || length <= 0 || (NSUInteger)(start + length) > sizeof(storage)) continue;
          NSData *opus = [NSData dataWithBytes:storage + start length:(NSUInteger)length];
          NSData *framed = OmiAmbientFramePacket(self.segmentSequence, opus);
          self.segmentSequence = (self.segmentSequence + 1) & 0xffff;
          [self.segmentPackets addObject:framed];
          self.segmentBytes += framed.length;
          self.writtenBytes += framed.length;
          self.chunks += 1;
        }
        if (packets == 0) break; // encoder buffering; the next tap delivers more
      }
    }
  }
}
- (void)closeActiveSegment {
  // Caller holds the lock; file IO hops to the serial queue.
  NSArray<NSData *> *packets = self.segmentPackets;
  NSDate *start = self.segmentStart;
  self.segmentPackets = nil;
  self.segmentStart = nil;
  if (packets.count == 0 || start == nil) return;
  NSString *uid = self.uid;
  int64_t capturedAtMs = (int64_t)(start.timeIntervalSince1970 * 1000.0);
  NSURL *root = self.root;
  dispatch_async(self.ioQueue, ^{
    OmiAmbientSpoolWrite(OmiAmbientSegmentDirectory(root, uid), OmiAmbientCodec, capturedAtMs, packets, nil);
    OmiAmbientSpoolPrune(OmiAmbientSegmentDirectory(root, uid));
  });
}
- (NSArray<NSDictionary *> *)pendingSegments {
  NSString *uid = nil;
  @synchronized(self) { uid = self.uid; }
  if (uid == nil) return @[];
  __block NSArray<NSDictionary *> *segments = @[];
  dispatch_sync(self.ioQueue, ^{
    segments = OmiAmbientSpoolList(OmiAmbientSegmentDirectory(self.root, uid));
  });
  return segments;
}
- (NSDictionary *)segmentPackets:(NSString *)identifier offset:(NSUInteger)offset limit:(NSUInteger)limit error:(NSError **)error {
  NSString *uid = nil;
  @synchronized(self) { uid = self.uid; }
  if (uid == nil) { if (error) *error = OmiAmbientError(@"OMI_CAPTURE_UNAUTHORIZED"); return nil; }
  __block NSDictionary *result = nil;
  __block NSError *failure = nil;
  dispatch_sync(self.ioQueue, ^{
    result = OmiAmbientSpoolRead(OmiAmbientSegmentDirectory(self.root, uid), identifier, offset, limit, &failure);
  });
  if (result == nil && error != nil) *error = failure ?: OmiAmbientError(@"OMI_CAPTURE_SEGMENT_MISSING");
  return result;
}
- (BOOL)acknowledgeSegment:(NSString *)identifier error:(NSError **)error {
  NSString *uid = nil;
  @synchronized(self) { uid = self.uid; }
  if (uid == nil) { if (error) *error = OmiAmbientError(@"OMI_CAPTURE_UNAUTHORIZED"); return NO; }
  __block BOOL removed = NO;
  __block NSError *failure = nil;
  dispatch_sync(self.ioQueue, ^{
    removed = OmiAmbientSpoolRemove(OmiAmbientSegmentDirectory(self.root, uid), identifier, &failure);
  });
  if (!removed && error != nil) *error = failure ?: OmiAmbientError(@"OMI_CAPTURE_SEGMENT_MISSING");
  return removed;
}
- (NSDictionary *)status {
  @synchronized(self) {
    return @{
      @"running": @(self.running && self.desired),
      @"sinceMs": self.startedAt == nil ? NSNull.null : @((long long)(self.startedAt.timeIntervalSince1970 * 1000.0)),
      @"chunks": @(self.chunks),
      @"bytes": @(self.writtenBytes),
      @"pendingSegments": @(self.pendingSegments.count),
      @"lastError": self.lastError ?: NSNull.null,
    };
  }
}
@end
