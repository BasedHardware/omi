#import "OmiAudioCapture.h"
#import <AVFoundation/AVFoundation.h>
#import <AppKit/AppKit.h>
#import <fcntl.h>
#import <unistd.h>
#import <sys/stat.h>

static NSString *const OmiAudioChunkPrefix = @"chunk-";
static NSString *const OmiAudioChunkExtension = @"m4a";
static const long long OmiAudioQuotaBytes = 512LL * 1024 * 1024;
static const NSTimeInterval OmiAudioChunkSeconds = 300.0;
static const double OmiAudioSampleRate = 16000.0;
static const NSInteger OmiAudioChannels = 1;
static const NSInteger OmiAudioBitRate = 24000;
static const AVAudioFrameCount OmiAudioTapBufferFrames = 8192;

static NSError *AudioError(NSString *code) {
  return [NSError errorWithDomain:code code:1 userInfo:nil];
}
static BOOL AudioIdentityValid(NSDictionary *identity) {
  NSString *uid = identity[@"uid"], *login = identity[@"login"];
  if (![uid isKindOfClass:NSString.class] || ![login isKindOfClass:NSString.class] || login.length == 0 || uid.length > 128) return NO;
  return [uid rangeOfString:@"^[A-Za-z0-9_-]+$" options:NSRegularExpressionSearch].location != NSNotFound;
}
static BOOL AudioDirectory(NSURL *url) {
  NSFileManager *files = NSFileManager.defaultManager;
  NSURL *current = [NSURL fileURLWithPath:@"/" isDirectory:YES];
  for (NSString *component in url.path.pathComponents) {
    if ([component isEqual:@"/"]) continue;
    current = [current URLByAppendingPathComponent:component isDirectory:YES];
    NSDictionary *attributes = [files attributesOfItemAtPath:current.path error:nil];
    if (attributes != nil) {
      if (![attributes[NSFileType] isEqual:NSFileTypeDirectory]) return NO;
    } else if (![files createDirectoryAtURL:current withIntermediateDirectories:NO attributes:@{NSFilePosixPermissions:@0700} error:nil]) return NO;
  }
  return YES;
}

@interface OmiAudioCapture ()
@property(nonatomic, copy) OmiAmbientIdentity identity;
@property(nonatomic, strong) NSURL *root;
@property(nonatomic, strong) dispatch_queue_t ioQueue;
@property(nonatomic, strong) NSMutableArray *observers;
@property(nonatomic, strong) AVAudioEngine *engine;
@property(nonatomic, strong) AVAudioFile *file;
@property(nonatomic, strong) NSDate *chunkStart;
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
        OmiAudioCapture *owner = weakSelf;
        if (owner == nil) return;
        @synchronized(owner) { if ([name isEqual:NSWorkspaceSessionDidResignActiveNotification]) owner.locked = YES; else owner.asleep = YES; }
        [owner pauseEngine];
      }];
      [_observers addObject:observer];
    }
    id lock = [NSDistributedNotificationCenter.defaultCenter addObserverForName:@"com.apple.screenIsLocked" object:nil queue:nil usingBlock:^(NSNotification *note) {
      OmiAudioCapture *owner = weakSelf;
      if (owner == nil) return;
      @synchronized(owner) { owner.locked = YES; }
      [owner pauseEngine];
    }];
    [_observers addObject:lock];
    for (NSString *name in @[NSWorkspaceDidWakeNotification, NSWorkspaceScreensDidWakeNotification, NSWorkspaceSessionDidBecomeActiveNotification]) {
      id observer = [NSWorkspace.sharedWorkspace.notificationCenter addObserverForName:name object:nil queue:nil usingBlock:^(NSNotification *note) {
        OmiAudioCapture *owner = weakSelf;
        if (owner == nil) return;
        @synchronized(owner) { if ([name isEqual:NSWorkspaceSessionDidBecomeActiveNotification]) owner.locked = NO; else owner.asleep = NO; }
        [owner resumeEngine];
      }];
      [_observers addObject:observer];
    }
    id unlock = [NSDistributedNotificationCenter.defaultCenter addObserverForName:@"com.apple.screenIsUnlocked" object:nil queue:nil usingBlock:^(NSNotification *note) {
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
    if (self.disposed || !AudioIdentityValid(owner)) { if (error) *error = AudioError(@"OMI_CAPTURE_UNAUTHORIZED"); return NO; }
    if (self.microphoneStatus != AVAuthorizationStatusAuthorized) { if (error) *error = AudioError(@"OMI_CAPTURE_PERMISSION"); return NO; }
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
    [self closeActiveFile];
    engine = self.engine;
    self.engine = nil;
  }
  // Tap removal happens outside the lock so an in-flight tap block waiting
  // on the same lock cannot deadlock with removeTapOnBus joining it.
  if (engine != nil) {
    @try { [engine.inputNode removeTapOnBus:0]; } @catch (NSException *failure) {}
    [engine stop];
  }
}
- (BOOL)resumeEngine {
  @synchronized(self) {
    if (self.disposed || self.running || !self.desired || self.locked || self.asleep) return YES;
    NSDictionary *owner = self.identity();
    if (!AudioIdentityValid(owner) || self.uid == nil || ![self.uid isEqual:owner[@"uid"]] || self.microphoneStatus != AVAuthorizationStatusAuthorized) return YES;
    AVAudioEngine *engine = [AVAudioEngine new];
    AVAudioFormat *inputFormat = [engine.inputNode outputFormatForBus:0];
    AVAudioFormat *targetFormat = [[AVAudioFormat alloc] initStandardFormatWithSampleRate:OmiAudioSampleRate channels:OmiAudioChannels];
    if (inputFormat == nil || targetFormat == nil || inputFormat.sampleRate < OmiAudioSampleRate || inputFormat.channelCount < 1) {
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
    __weak OmiAudioCapture *weakSelf = self;
    [engine.inputNode installTapOnBus:0 bufferSize:OmiAudioTapBufferFrames format:inputFormat block:^(AVAudioPCMBuffer *buffer, AVAudioTime *when) {
      OmiAudioCapture *owner = weakSelf;
      if (owner == nil) return;
      [owner writeSamples:buffer converter:converter];
    }];
    [engine prepare];
    NSError *failure = nil;
    if (![engine startAndReturnError:&failure]) {
      @try { [engine.inputNode removeTapOnBus:0]; } @catch (NSException *stopFailure) {}
      self.desired = NO;
      self.lastError = @"OMI_CAPTURE_UNAVAILABLE";
      return NO;
    }
    self.engine = engine;
    self.running = YES;
    self.startedAt = NSDate.date;
    return YES;
  }
}
- (void)writeSamples:(AVAudioPCMBuffer *)buffer converter:(AVAudioConverter *)converter {
  @synchronized(self) {
    if (!self.running) return;
    NSDate *now = NSDate.date;
    if (self.file == nil || (self.chunkStart != nil && [now timeIntervalSinceDate:self.chunkStart] >= OmiAudioChunkSeconds)) {
      [self closeActiveFile];
      if (![self openActiveFileAt:now]) {
        self.lastError = @"OMI_CAPTURE_STORAGE";
        return;
      }
      __weak OmiAudioCapture *weakSelf = self;
      dispatch_async(self.ioQueue, ^{
        OmiAudioCapture *owner = weakSelf;
        if (owner != nil) [owner pruneToQuota];
      });
    }
    if (self.file == nil) return;
    NSError *failure = nil;
    AVAudioFrameCount capacity = (AVAudioFrameCount)ceil(buffer.frameLength * OmiAudioSampleRate / converter.inputFormat.sampleRate) + 16;
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
      if (output.frameLength == 0 || self.file == nil) continue;
      if (![self.file writeFromBuffer:output error:&failure]) {
        [self closeActiveFile];
        self.lastError = @"OMI_CAPTURE_STORAGE";
        return;
      }
      self.writtenBytes += (long long)ceil(output.frameLength * (double)OmiAudioBitRate / OmiAudioSampleRate / 8.0);
    }
  }
}
- (BOOL)openActiveFileAt:(NSDate *)timestamp {
  NSURL *directory = [[[[self.root URLByAppendingPathComponent:@"users"] URLByAppendingPathComponent:self.uid] URLByAppendingPathComponent:@"audio"] copy];
  if (!AudioDirectory(directory)) return NO;
  NSString *name = [NSString stringWithFormat:@"%@%.0f.%@", OmiAudioChunkPrefix, [timestamp timeIntervalSince1970] * 1000.0, OmiAudioChunkExtension];
  NSURL *url = [directory URLByAppendingPathComponent:name];
  NSError *failure = nil;
  AVAudioFile *file = [[AVAudioFile alloc] initForWriting:url settings:@{
    AVFormatIDKey: @(kAudioFormatMPEG4AAC),
    AVSampleRateKey: @(OmiAudioSampleRate),
    AVNumberOfChannelsKey: @(OmiAudioChannels),
    AVEncoderBitRateKey: @(OmiAudioBitRate),
  } commonFormat:AVAudioPCMFormatFloat32 interleaved:NO error:&failure];
  if (file == nil) return NO;
  self.file = file;
  self.chunkStart = timestamp;
  self.chunks += 1;
  return YES;
}
- (void)closeActiveFile {
  self.file = nil;
  self.chunkStart = nil;
}
- (void)pruneToQuota {
  @synchronized(self) {
    if (self.disposed) return;
  }
  NSFileManager *files = NSFileManager.defaultManager;
  NSURL *directory = [[[[self.root URLByAppendingPathComponent:@"users"] URLByAppendingPathComponent:self.uid] URLByAppendingPathComponent:@"audio"] copy];
  NSArray<NSURL *> *contents = [files contentsOfDirectoryAtURL:directory includingPropertiesForKeys:@[NSURLFileSizeKey, NSURLIsSymbolicLinkKey] options:0 error:nil];
  if (contents == nil) return;
  NSMutableArray *chunks = [NSMutableArray new];
  for (NSURL *url in contents) {
    if (![url.lastPathComponent hasPrefix:OmiAudioChunkPrefix] || ![url.pathExtension.lowercaseString isEqual:OmiAudioChunkExtension]) continue;
    NSNumber *link = nil, *bytes = nil;
    [url getResourceValue:&link forKey:NSURLIsSymbolicLinkKey error:nil];
    if (link.boolValue) continue;
    [url getResourceValue:&bytes forKey:NSURLFileSizeKey error:nil];
    [chunks addObject:@{@"url": url, @"size": bytes ?: @0}];
  }
  [chunks sortUsingComparator:^NSComparisonResult(NSDictionary *left, NSDictionary *right) {
    return [((NSURL *)left[@"url"]).lastPathComponent compare:((NSURL *)right[@"url"]).lastPathComponent options:NSNumericSearch];
  }];
  unsigned long long total = 0;
  for (NSDictionary *chunk in chunks) total += [chunk[@"size"] unsignedLongLongValue];
  for (NSDictionary *chunk in chunks) {
    if (total <= (unsigned long long)OmiAudioQuotaBytes) break;
    if ([files removeItemAtURL:chunk[@"url"] error:nil]) total -= [chunk[@"size"] unsignedLongLongValue];
  }
  @synchronized(self) { self.writtenBytes = (long long)total; }
}
- (NSDictionary *)status {
  @synchronized(self) {
    return @{
      @"running": @(self.running && self.desired),
      @"sinceMs": self.startedAt == nil ? NSNull.null : @((long long)(self.startedAt.timeIntervalSince1970 * 1000.0)),
      @"chunks": @(self.chunks),
      @"bytes": @(self.writtenBytes),
      @"lastError": self.lastError ?: NSNull.null,
    };
  }
}
@end
