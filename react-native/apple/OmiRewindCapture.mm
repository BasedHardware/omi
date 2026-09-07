#import "OmiRewindCapture.h"
#import <AppKit/AppKit.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <Vision/Vision.h>
#import <ImageIO/ImageIO.h>
#import <sqlite3.h>
#import <fcntl.h>
#import <unistd.h>
#import <sys/stat.h>

static BOOL CaptureGrantAtProcessStart = NO;

static NSError *CaptureError(NSString *code) {
  return [NSError errorWithDomain:code code:1 userInfo:nil];
}
static BOOL CaptureIdentityValid(NSDictionary *identity) {
  NSString *uid = identity[@"uid"], *login = identity[@"login"];
  if (![uid isKindOfClass:NSString.class] || ![login isKindOfClass:NSString.class] || login.length == 0 || uid.length > 128) return NO;
  return [uid rangeOfString:@"^[A-Za-z0-9_-]+$" options:NSRegularExpressionSearch].location != NSNotFound;
}
static BOOL CaptureExcluded(NSString *name) {
  NSSet *defaults = [NSSet setWithArray:@[@"Omi Computer", @"Omi Beta", @"Omi", @"Omi Dev", @"Passwords", @"1Password", @"1Password 7", @"Bitwarden", @"LastPass", @"Dashlane", @"Keeper", @"Enpass", @"KeePassXC", @"Keychain Access"]];
  if (name.length == 0 || [defaults containsObject:name]) return YES;
  for (NSDictionary *preferences in @[[NSUserDefaults.standardUserDefaults persistentDomainForName:@"com.omi.computer-macos"] ?: @{}, NSUserDefaults.standardUserDefaults.dictionaryRepresentation]) {
    id excluded = preferences[@"rewindExcludedApps"];
    if ([excluded isKindOfClass:NSArray.class] && [excluded containsObject:name]) return YES;
  }
  return NO;
}
static BOOL CaptureDirectory(NSURL *url) {
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
static void CaptureSource(void (^completion)(CGImageRef, NSString *, NSString *, NSError *)) {
  dispatch_async(dispatch_get_main_queue(), ^{
    NSRunningApplication *app = NSWorkspace.sharedWorkspace.frontmostApplication;
    NSString *name = app.localizedName;
    if (app == nil || app.processIdentifier == NSProcessInfo.processInfo.processIdentifier || CaptureExcluded(name)) { completion(nil, name, nil, nil); return; }
    pid_t pid = app.processIdentifier;
    CFArrayRef raw = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, kCGNullWindowID);
    NSArray *windows = CFBridgingRelease(raw);
    NSNumber *target = nil;
    for (NSDictionary *window in windows) {
      if ([window[(id)kCGWindowOwnerPID] intValue] == pid && [window[(id)kCGWindowLayer] intValue] == 0 && [window[(id)kCGWindowAlpha] doubleValue] > 0) { target = window[(id)kCGWindowNumber]; break; }
    }
    if (target == nil) { completion(nil, name, nil, nil); return; }
    if (@available(macOS 14.0, *)) {
      [SCShareableContent getShareableContentExcludingDesktopWindows:YES onScreenWindowsOnly:YES completionHandler:^(SCShareableContent *content, NSError *error) {
        if (error != nil) { completion(nil, nil, nil, CaptureError(@"OMI_CAPTURE_UNAVAILABLE")); return; }
        dispatch_async(dispatch_get_main_queue(), ^{
          if (NSWorkspace.sharedWorkspace.frontmostApplication.processIdentifier != pid || CaptureExcluded(name)) { completion(nil, name, nil, nil); return; }
          SCWindow *selected = nil;
          for (SCWindow *window in content.windows) if (window.windowID == target.unsignedIntValue) { selected = window; break; }
          if (selected == nil || selected.frame.size.width <= 0 || selected.frame.size.height <= 0) { completion(nil, name, nil, nil); return; }
          SCStreamConfiguration *configuration = [SCStreamConfiguration new];
          double scale = fmin(1.0, 2304.0 / fmax(selected.frame.size.width, selected.frame.size.height));
          configuration.width = MAX(1, (size_t)(selected.frame.size.width * scale));
          configuration.height = MAX(1, (size_t)(selected.frame.size.height * scale));
          configuration.showsCursor = NO;
          SCContentFilter *filter = [[SCContentFilter alloc] initWithDesktopIndependentWindow:selected];
          [SCScreenshotManager captureImageWithFilter:filter configuration:configuration completionHandler:^(CGImageRef image, NSError *captureError) {
            completion(image, name, selected.title, captureError == nil ? nil : CaptureError(@"OMI_CAPTURE_UNAVAILABLE"));
          }];
        });
      }];
    } else completion(nil, nil, nil, CaptureError(@"OMI_CAPTURE_UNSUPPORTED"));
  });
}

@interface OmiRewindCapture ()
@property(nonatomic, copy) OmiRewindIdentity identity;
@property(nonatomic, copy) OmiRewindFrameSource source;
@property(nonatomic, copy) BOOL (^permission)(void);
@property(nonatomic, strong) NSURL *root;
@property(nonatomic, strong) id authorityLock;
@property(nonatomic, strong) NSDictionary *owner;
@property(nonatomic) NSUInteger generation;
@property(nonatomic) BOOL enabled;
@property(nonatomic) BOOL disposed;
@property(nonatomic) BOOL busy;
@property(nonatomic) BOOL processing;
@property(nonatomic) BOOL locked;
@property(nonatomic) BOOL asleep;
@property(nonatomic) BOOL grantAtLaunch;
@property(nonatomic, strong) dispatch_queue_t queue;
@property(nonatomic, strong) NSMutableArray *observers;
@end

@implementation OmiRewindCapture
+ (void)load { CaptureGrantAtProcessStart = CGPreflightScreenCaptureAccess(); }
- (instancetype)initWithIdentity:(OmiRewindIdentity)identity root:(NSURL *)root authorityLock:(id)authorityLock {
  self = [self initWithIdentity:identity root:root source:^(void (^completion)(CGImageRef, NSString *, NSString *, NSError *)) { CaptureSource(completion); } permission:^BOOL { return CGPreflightScreenCaptureAccess(); }];
  if (self) { self.grantAtLaunch = CaptureGrantAtProcessStart; self.authorityLock = authorityLock; }
  return self;
}
- (instancetype)initWithIdentity:(OmiRewindIdentity)identity root:(NSURL *)root source:(OmiRewindFrameSource)source permission:(BOOL (^)(void))permission {
  self = [super init];
  if (self) {
    _identity = [identity copy]; _root = root; _authorityLock = [NSObject new]; _source = [source copy]; _permission = [permission copy]; _grantAtLaunch = permission();
    _queue = dispatch_queue_create("omi.rewind.capture", DISPATCH_QUEUE_SERIAL); _observers = [NSMutableArray new];
    __weak OmiRewindCapture *weakSelf = self;
    for (NSString *name in @[NSWorkspaceWillSleepNotification, NSWorkspaceSessionDidResignActiveNotification, NSWorkspaceScreensDidSleepNotification]) {
      id observer = [NSWorkspace.sharedWorkspace.notificationCenter addObserverForName:name object:nil queue:nil usingBlock:^(NSNotification *note) {
        OmiRewindCapture *owner = weakSelf;
        @synchronized(owner) { if ([name isEqual:NSWorkspaceSessionDidResignActiveNotification]) owner.locked = YES; else owner.asleep = YES; }
        [owner stopCapture];
      }];
      [_observers addObject:observer];
    }
    id lock = [NSDistributedNotificationCenter.defaultCenter addObserverForName:@"com.apple.screenIsLocked" object:nil queue:nil usingBlock:^(NSNotification *note) { OmiRewindCapture *owner = weakSelf; @synchronized(owner) { owner.locked = YES; } [owner stopCapture]; }];
    [_observers addObject:lock];
    for (NSString *name in @[NSWorkspaceDidWakeNotification, NSWorkspaceScreensDidWakeNotification, NSWorkspaceSessionDidBecomeActiveNotification]) {
      id observer = [NSWorkspace.sharedWorkspace.notificationCenter addObserverForName:name object:nil queue:nil usingBlock:^(NSNotification *note) {
        OmiRewindCapture *owner = weakSelf;
        @synchronized(owner) { if ([name isEqual:NSWorkspaceSessionDidBecomeActiveNotification]) owner.locked = NO; else owner.asleep = NO; }
      }];
      [_observers addObject:observer];
    }
    id unlock = [NSDistributedNotificationCenter.defaultCenter addObserverForName:@"com.apple.screenIsUnlocked" object:nil queue:nil usingBlock:^(NSNotification *note) { OmiRewindCapture *owner = weakSelf; @synchronized(owner) { owner.locked = NO; } }];
    [_observers addObject:unlock];
  }
  return self;
}
- (NSString *)requestCapturePermission {
  if (@available(macOS 14.0, *)) {
    @synchronized(self) { if (self.disposed) return @"denied"; }
    if (!self.permission()) { CGRequestScreenCaptureAccess(); if (!self.permission()) return @"denied"; }
    return self.grantAtLaunch ? @"granted" : @"restartRequired";
  }
  return @"unsupported";
}
- (BOOL)startCapture:(NSError **)error {
  if (@available(macOS 14.0, *)) {} else { if (error) *error = CaptureError(@"OMI_CAPTURE_UNSUPPORTED"); return NO; }
  @synchronized(self) {
    NSDictionary *owner = self.identity();
    if (self.disposed || self.locked || self.asleep || !CaptureIdentityValid(owner)) { if (error) *error = CaptureError(@"OMI_CAPTURE_UNAUTHORIZED"); return NO; }
    if (!self.permission() || !self.grantAtLaunch) { if (error) *error = CaptureError(@"OMI_CAPTURE_PERMISSION"); return NO; }
    self.generation++; self.owner = owner; self.enabled = YES; self.busy = NO;
    return YES;
  }
}
- (void)stopCapture { @synchronized(self) { self.generation++; self.enabled = NO; self.owner = nil; self.busy = NO; } }
- (void)invalidate { @synchronized(self) { self.disposed = YES; [self stopCapture]; } }
- (void)dealloc {
  for (id observer in self.observers) {
    [NSWorkspace.sharedWorkspace.notificationCenter removeObserver:observer];
    [NSDistributedNotificationCenter.defaultCenter removeObserver:observer];
  }
}
- (BOOL)current:(NSUInteger)generation owner:(NSDictionary *)owner {
  @synchronized(self) { return !self.disposed && !self.locked && !self.asleep && self.enabled && self.generation == generation && [self.identity() isEqual:owner] && self.permission(); }
}
- (NSTimeInterval)captureTimeout { return 15; }
- (void)captureFrame:(OmiRewindCaptureCompletion)completion {
  __block NSUInteger generation;
  __block NSDictionary *owner;
  @synchronized(self) {
    if (!self.enabled || self.disposed || self.busy || self.processing || ![self.identity() isEqual:self.owner]) { completion(nil, CaptureError(@"OMI_CAPTURE_STOPPED")); return; }
    self.busy = YES; generation = self.generation; owner = self.owner;
  }
  NSObject *settlement = [NSObject new];
  __block BOOL settled = NO;
  OmiRewindCaptureCompletion finish = ^(NSDictionary *value, NSError *error) {
    @synchronized(settlement) { if (settled) return; settled = YES; }
    completion(value, error);
  };
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)([self captureTimeout] * NSEC_PER_SEC)), dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
    @synchronized(settlement) {
      if (settled) return;
      @synchronized(self) { if (self.generation == generation) [self stopCapture]; }
      finish(nil, CaptureError(@"OMI_CAPTURE_TIMEOUT"));
    }
  });
  self.source(^(CGImageRef image, NSString *appName, NSString *title, NSError *sourceError) {
    @synchronized(settlement) { if (settled) return; }
    BOOL accepted = NO;
    @synchronized(self) { accepted = [self current:generation owner:owner]; if (accepted) self.processing = YES; }
    if (!accepted) { finish(nil, CaptureError(@"OMI_CAPTURE_STOPPED")); return; }
    NSDate *timestamp = NSDate.date;
    if (appName.length > 256 || title.length > 1024) sourceError = CaptureError(@"OMI_CAPTURE_METADATA");
    if (image != nil) CGImageRetain(image);
    dispatch_async(self.queue, ^{
      @autoreleasepool {
        NSError *error = sourceError;
        BOOL captured = NO;
        @synchronized(self) { if (![self current:generation owner:owner]) error = CaptureError(@"OMI_CAPTURE_STOPPED"); }
        if (error == nil && image != nil && !CaptureExcluded(appName)) {
          NSMutableData *jpeg = [NSMutableData new];
          CGImageDestinationRef destination = CGImageDestinationCreateWithData((__bridge CFMutableDataRef)jpeg, CFSTR("public.jpeg"), 1, nil);
          if (destination != nil) {
            CGImageDestinationAddImage(destination, image, (__bridge CFDictionaryRef)@{(id)kCGImageDestinationLossyCompressionQuality:@0.8});
            if (!CGImageDestinationFinalize(destination)) error = CaptureError(@"OMI_CAPTURE_IMAGE");
            CFRelease(destination);
          } else error = CaptureError(@"OMI_CAPTURE_IMAGE");
          VNRecognizeTextRequest *request = [VNRecognizeTextRequest new];
          request.recognitionLevel = VNRequestTextRecognitionLevelFast;
          request.automaticallyDetectsLanguage = YES;
          VNImageRequestHandler *handler = [[VNImageRequestHandler alloc] initWithCGImage:image options:@{}];
          if (error == nil && ![handler performRequests:@[request] error:nil]) error = CaptureError(@"OMI_CAPTURE_OCR");
          NSMutableArray *lines = [NSMutableArray new];
          NSUInteger characters = 0;
          for (VNRecognizedTextObservation *observation in request.results) {
            NSString *line = [observation topCandidates:1].firstObject.string;
            if (line != nil && (characters += line.length) <= 1000000) [lines addObject:line];
          }
          @synchronized(self) { if (![self current:generation owner:owner]) error = CaptureError(@"OMI_CAPTURE_STOPPED"); }
          if (error == nil && !CaptureExcluded(appName)) captured = [self persistJPEG:jpeg text:[lines componentsJoinedByString:@"\n"] app:appName title:title timestamp:timestamp owner:owner generation:generation error:&error];
        }
        if (image != nil) CGImageRelease(image);
        @synchronized(self) { self.processing = NO; if (self.generation == generation) self.busy = NO; if (![self current:generation owner:owner]) error = CaptureError(@"OMI_CAPTURE_STOPPED"); }
        finish(error == nil ? @{@"captured":@(captured)} : nil, error);
      }
    });
  });
}
- (BOOL)persistJPEG:(NSData *)jpeg text:(NSString *)text app:(NSString *)app title:(NSString *)title timestamp:(NSDate *)timestamp owner:(NSDictionary *)owner generation:(NSUInteger)generation error:(NSError **)error {
  NSFileManager *files = NSFileManager.defaultManager;
  NSURL *directory = [[self.root URLByAppendingPathComponent:@"users"] URLByAppendingPathComponent:owner[@"uid"]];
  NSURL *screens = [directory URLByAppendingPathComponent:@"Screenshots"];
  if (jpeg.length == 0 || jpeg.length > 8388608 || !CaptureDirectory(screens)) { *error = CaptureError(@"OMI_CAPTURE_STORAGE"); return NO; }
  NSURL *database = [directory URLByAppendingPathComponent:@"omi.db"];
  sqlite3 *db = nullptr;
  if (sqlite3_open_v2(database.path.UTF8String, &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_NOFOLLOW, nullptr) != SQLITE_OK) { if (db) sqlite3_close(db); *error = CaptureError(@"OMI_CAPTURE_STORAGE"); return NO; }
  chmod(database.path.fileSystemRepresentation, 0600);
  sqlite3_busy_timeout(db, 1000);
  BOOL success = NO;
  NSString *filename = [NSUUID.UUID.UUIDString stringByAppendingString:@".jpg"];
  NSURL *imageURL = [screens URLByAppendingPathComponent:filename];
  @try {
    if (sqlite3_exec(db, "CREATE TABLE IF NOT EXISTS screenshots(id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp TEXT NOT NULL,appName TEXT NOT NULL,windowTitle TEXT,imagePath TEXT NOT NULL,videoChunkPath TEXT,frameOffset INTEGER,ocrText TEXT,isIndexed INTEGER NOT NULL DEFAULT 1)", nullptr, nullptr, nullptr) != SQLITE_OK) return NO;
    NSDateFormatter *formatter = [NSDateFormatter new]; formatter.locale = [NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"]; formatter.timeZone = [NSTimeZone timeZoneForSecondsFromGMT:0]; formatter.dateFormat = @"yyyy-MM-dd HH:mm:ss.SSS";
    id retention = [NSUserDefaults.standardUserDefaults objectForKey:@"rewindRetentionDays"];
    NSInteger days = retention == nil ? 14 : ([retention isKindOfClass:NSNumber.class] && [@[@0,@7,@14,@30] containsObject:retention] ? [retention integerValue] : 0);
    NSString *cutoff = days > 0 ? [formatter stringFromDate:[NSDate dateWithTimeIntervalSinceNow:-days * 86400]] : @"";
    sqlite3_stmt *expired = nullptr;
    NSMutableArray *oldPaths = [NSMutableArray new];
    if (sqlite3_prepare_v2(db, "SELECT imagePath FROM screenshots WHERE timestamp < ? LIMIT 1000", -1, &expired, nullptr) == SQLITE_OK) {
      sqlite3_bind_text(expired, 1, cutoff.UTF8String, -1, SQLITE_TRANSIENT);
      while (sqlite3_step(expired) == SQLITE_ROW) {
        if (![self current:generation owner:owner]) break;
        const char *raw = (const char *)sqlite3_column_text(expired, 0);
        if (raw) [oldPaths addObject:[NSString stringWithUTF8String:raw]];
      }
    }
    sqlite3_finalize(expired);
    if (![self current:generation owner:owner]) { *error = CaptureError(@"OMI_CAPTURE_STOPPED"); return NO; }
    for (NSString *path in oldPaths) {
      if (![self current:generation owner:owner]) { *error = CaptureError(@"OMI_CAPTURE_STOPPED"); return NO; }
      if (![path.lastPathComponent isEqual:path] || ![path.pathExtension isEqual:@"jpg"]) continue;
      sqlite3_stmt *remove = nullptr;
      if (sqlite3_prepare_v2(db, "DELETE FROM screenshots WHERE imagePath=? AND timestamp<?", -1, &remove, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(remove, 1, path.UTF8String, -1, SQLITE_TRANSIENT); sqlite3_bind_text(remove, 2, cutoff.UTF8String, -1, SQLITE_TRANSIENT);
        if (sqlite3_step(remove) == SQLITE_DONE) [files removeItemAtURL:[screens URLByAppendingPathComponent:path] error:nil];
      }
      sqlite3_finalize(remove);
    }
    unsigned long long size = 0;
    NSUInteger count = 0;
    __block BOOL walkFailed = NO;
    NSDirectoryEnumerator *entries = [files enumeratorAtURL:self.root includingPropertiesForKeys:@[NSURLFileSizeKey, NSURLIsSymbolicLinkKey] options:0 errorHandler:^BOOL(NSURL *url, NSError *failure) { walkFailed = YES; return NO; }];
    for (NSURL *url in entries) {
      if (![self current:generation owner:owner]) { *error = CaptureError(@"OMI_CAPTURE_STOPPED"); return NO; }
      NSNumber *bytes = nil, *link = nil;
      [url getResourceValue:&link forKey:NSURLIsSymbolicLinkKey error:nil];
      if (link.boolValue || ++count > 200000) { *error = CaptureError(@"OMI_CAPTURE_STORAGE"); return NO; }
      [url getResourceValue:&bytes forKey:NSURLFileSizeKey error:nil]; size += bytes.unsignedLongLongValue;
      if (size + jpeg.length + 8388608 > 1073741824) { *error = CaptureError(@"OMI_CAPTURE_QUOTA"); return NO; }
    }
    if (walkFailed || entries == nil) { *error = CaptureError(@"OMI_CAPTURE_STORAGE"); return NO; }
    int fd = open(imageURL.path.fileSystemRepresentation, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW, 0600);
    if (fd < 0) return NO;
    size_t offset = 0;
    while (offset < jpeg.length) { ssize_t wrote = write(fd, (const char *)jpeg.bytes + offset, jpeg.length - offset); if (wrote <= 0) break; offset += wrote; }
    BOOL durable = offset == jpeg.length && fsync(fd) == 0; close(fd);
    if (!durable) return NO;
    int directoryFD = open(screens.path.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW);
    BOOL directoryDurable = directoryFD >= 0 && fsync(directoryFD) == 0;
    if (directoryFD >= 0) close(directoryFD);
    if (!directoryDurable) return NO;
    @synchronized(self) {
    @synchronized(self.authorityLock) {
      if (![self current:generation owner:owner] || CaptureExcluded(app)) { *error = CaptureError(@"OMI_CAPTURE_STOPPED"); return NO; }
      if (sqlite3_exec(db, "BEGIN IMMEDIATE", nullptr, nullptr, nullptr) != SQLITE_OK) return NO;
      sqlite3_stmt *insert = nullptr;
      if (sqlite3_prepare_v2(db, "INSERT INTO screenshots(timestamp,appName,windowTitle,imagePath,ocrText) VALUES(?,?,?,?,?)", -1, &insert, nullptr) == SQLITE_OK) {
        NSArray *values = @[[formatter stringFromDate:timestamp], app, title ?: @"", filename, text];
        for (int index = 0; index < 5; index++) sqlite3_bind_text(insert, index + 1, [values[index] UTF8String], -1, SQLITE_TRANSIENT);
        success = sqlite3_step(insert) == SQLITE_DONE;
      }
      sqlite3_finalize(insert);
      success = success && [self current:generation owner:owner];
      if (success) success = sqlite3_exec(db, "COMMIT", nullptr, nullptr, nullptr) == SQLITE_OK;
      if (!success) sqlite3_exec(db, "ROLLBACK", nullptr, nullptr, nullptr);
    }
    }
    return success;
  } @finally {
    sqlite3_close(db);
    if (!success) { [files removeItemAtURL:imageURL error:nil]; if (*error == nil) *error = CaptureError(@"OMI_CAPTURE_STORAGE"); }
  }
}
@end
