#import "../RnRuntime-macOS/OmiRewindStore.h"
#include <cassert>
static void requireAt(BOOL value, int line) { if (!value) { fprintf(stderr, "Rewind store assertion failed at line %d\n", line); abort(); } }
#define require(...) requireAt((__VA_ARGS__), __LINE__)

static NSData *fixtureJPEG(void) {
  unsigned char pixels[16 * 16 * 4];
  for (NSUInteger i = 0; i < sizeof(pixels); i += 4) { pixels[i]=40; pixels[i+1]=150; pixels[i+2]=170; pixels[i+3]=255; }
  CGColorSpaceRef colors = CGColorSpaceCreateDeviceRGB();
  CGContextRef context = CGBitmapContextCreate(pixels, 16, 16, 8, 64, colors, kCGImageAlphaPremultipliedLast);
  CGImageRef image = CGBitmapContextCreateImage(context);
  NSMutableData *data = [NSMutableData data];
  CGImageDestinationRef destination = CGImageDestinationCreateWithData((__bridge CFMutableDataRef)data, CFSTR("public.jpeg"), 1, NULL);
  CGImageDestinationAddImage(destination, image, NULL); require(CGImageDestinationFinalize(destination));
  CFRelease(destination); CGImageRelease(image); CGContextRelease(context); CGColorSpaceRelease(colors);
  return data;
}
static void fixtureVideo(NSString *path) {
  AVAssetWriter *writer = [[AVAssetWriter alloc] initWithURL:[NSURL fileURLWithPath:path] fileType:AVFileTypeQuickTimeMovie error:nil];
  AVAssetWriterInput *input = [[AVAssetWriterInput alloc] initWithMediaType:AVMediaTypeVideo outputSettings:@{AVVideoCodecKey:AVVideoCodecTypeHEVC,AVVideoWidthKey:@64,AVVideoHeightKey:@64}];
  AVAssetWriterInputPixelBufferAdaptor *adaptor = [AVAssetWriterInputPixelBufferAdaptor assetWriterInputPixelBufferAdaptorWithAssetWriterInput:input sourcePixelBufferAttributes:@{(__bridge id)kCVPixelBufferPixelFormatTypeKey:@(kCVPixelFormatType_32BGRA),(__bridge id)kCVPixelBufferWidthKey:@64,(__bridge id)kCVPixelBufferHeightKey:@64}];
  require([writer canAddInput:input]); [writer addInput:input]; require([writer startWriting]); [writer startSessionAtSourceTime:kCMTimeZero];
  dispatch_semaphore_t finished = dispatch_semaphore_create(0);
  __block int index = 0; __block BOOL ending = NO;
  [input requestMediaDataWhenReadyOnQueue:dispatch_queue_create("rewind.video.fixture", DISPATCH_QUEUE_SERIAL) usingBlock:^{
    if (ending) return;
    while (input.readyForMoreMediaData && index < 2) {
      CVPixelBufferRef buffer = NULL; require(CVPixelBufferPoolCreatePixelBuffer(NULL, adaptor.pixelBufferPool, &buffer) == kCVReturnSuccess);
      CVPixelBufferLockBaseAddress(buffer, 0);
      for (size_t y = 0; y < 64; y++) {
        unsigned char *row = (unsigned char *)CVPixelBufferGetBaseAddress(buffer) + y * CVPixelBufferGetBytesPerRow(buffer);
        for (size_t x = 0; x < 64; x++) { row[x*4] = index == 0 ? 0 : 255; row[x*4+1] = 0; row[x*4+2] = index == 0 ? 255 : 0; row[x*4+3] = 255; }
      }
      CVPixelBufferUnlockBaseAddress(buffer, 0);
      require([adaptor appendPixelBuffer:buffer withPresentationTime:CMTimeMake(index, 1)]); CVPixelBufferRelease(buffer); index++;
    }
    if (index == 2) { ending = YES; [input markAsFinished]; [writer finishWritingWithCompletionHandler:^{ dispatch_semaphore_signal(finished); }]; }
  }];
  require(dispatch_semaphore_wait(finished, dispatch_time(DISPATCH_TIME_NOW, 10 * NSEC_PER_SEC)) == 0);
  require(writer.status == AVAssetWriterStatusCompleted);
}

int main(void) {
  @autoreleasepool {
    NSString *root = [@"/Users/Shared" stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    NSString *folder = [root stringByAppendingPathComponent:@"owner-a"];
    require([NSFileManager.defaultManager createDirectoryAtPath:[folder stringByAppendingPathComponent:@"Screenshots"] withIntermediateDirectories:YES attributes:nil error:nil]);
    NSString *dbPath = [folder stringByAppendingPathComponent:@"omi.db"];
    sqlite3 *db = NULL; require(sqlite3_open(dbPath.UTF8String, &db) == SQLITE_OK);
    require(sqlite3_exec(db, "CREATE TABLE screenshots(id INTEGER PRIMARY KEY,timestamp TEXT,appName TEXT,windowTitle TEXT,imagePath TEXT,videoChunkPath TEXT,frameOffset INTEGER,ocrText TEXT); INSERT INTO screenshots VALUES(1,'2026-09-07 01:02:03.123','100% Studio','First','frame.jpg',NULL,NULL,'literal search'),(2,'2026-09-07 01:02:03.123','Editor','Second','../escape.jpg',NULL,NULL,'work'),(3,'2026-09-07 01:02:03.123','Browser','Third','frame.jpg',NULL,NULL,'notes');", NULL,NULL,NULL)==SQLITE_OK);
    sqlite3_close(db);
    NSData *jpeg = fixtureJPEG(); require([jpeg writeToFile:[folder stringByAppendingPathComponent:@"Screenshots/frame.jpg"] atomically:YES]);
    NSData *before = [NSData dataWithContentsOfFile:dbPath];
    __block NSDictionary *identity = @{@"uid":@"owner-a",@"login":@"login-a"};
    OmiRewindStore *store = [[OmiRewindStore alloc] initWithRoot:root identity:^{return identity;}];
    NSError *listError = nil;
    NSDictionary *page = [store list:@{@"query":@"",@"limit":@2,@"cursor":NSNull.null} error:&listError];
    if (listError) fprintf(stderr, "List fixture error: %s\n", listError.localizedDescription.UTF8String);
    require([page[@"frames"] count] == 2 && [page[@"nextCursor"] isKindOfClass:NSString.class]);
    NSDictionary *next = [store list:@{@"query":@"",@"limit":@2,@"cursor":page[@"nextCursor"]} error:nil];
    require([next[@"frames"] count] == 1 && next[@"nextCursor"] == NSNull.null);
    NSString *identifier = next[@"frames"][0][@"id"];
    NSDictionary *read = [store read:identifier error:nil];
    require([read[@"mimeType"] isEqual:@"image/jpeg"] && [read[@"base64"] length] > 0);
    require([store read:page[@"frames"][1][@"id"] error:nil] == nil);
    NSDictionary *literal = [store list:@{@"query":@"%",@"limit":@50} error:nil];
    require([literal[@"frames"] count] == 1);
    require([store list:@{@"query":@"changed",@"limit":@2,@"cursor":page[@"nextCursor"]} error:nil] == nil);
    identity = @{@"uid":@"owner-b",@"login":@"login-b"};
    require([store read:identifier error:nil] == nil);
    require([store list:@{@"query":@"",@"limit":@2,@"cursor":page[@"nextCursor"]} error:nil] == nil);
    identity = @{@"uid":@"owner-a",@"login":@"login-a"};
    __block NSUInteger checks = 0;
    OmiRewindStore *retired = [[OmiRewindStore alloc] initWithRoot:root identity:^{ checks++; return checks < 3 ? identity : @{@"uid":@"owner-b",@"login":@"login-b"}; }];
    require([retired list:@{@"query":@"",@"limit":@2} error:nil] == nil);
    require([[NSData dataWithContentsOfFile:dbPath] isEqual:before]);
    require([NSFileManager.defaultManager createDirectoryAtPath:[folder stringByAppendingPathComponent:@"Videos"] withIntermediateDirectories:YES attributes:nil error:nil]);
    fixtureVideo([folder stringByAppendingPathComponent:@"Videos/fixture.mov"]);
    require(sqlite3_open(dbPath.UTF8String, &db) == SQLITE_OK);
    require(sqlite3_exec(db, "INSERT INTO screenshots VALUES(4,'2026-09-07 02:00:00.000','Video','Red',NULL,'fixture.mov',0,NULL),(5,'2026-09-07 02:00:01.000','Video','Blue',NULL,'fixture.mov',1,NULL)",NULL,NULL,NULL) == SQLITE_OK); sqlite3_close(db);
    before = [NSData dataWithContentsOfFile:dbPath];
    NSDictionary *videos = [store list:@{@"query":@"Video",@"limit":@2} error:nil];
    require([videos[@"frames"] count] == 2);
    NSDictionary *first = [store read:videos[@"frames"][0][@"id"] error:nil];
    NSDictionary *second = [store read:videos[@"frames"][1][@"id"] error:nil];
    require(first != nil && second != nil && ![first[@"base64"] isEqual:second[@"base64"]]);
    store.disposed = YES; require([store read:identifier error:nil] == nil);
    require([[NSData dataWithContentsOfFile:dbPath] isEqual:before]);
    store.disposed = NO;
    NSDictionary *request = @{@"query":@"",@"limit":@50};
    // Missing history is normal; malformed or unreadable existing history is
    // not. Exercise the actual SQLite boundary and native timeline error codes.
    require([NSFileManager.defaultManager removeItemAtPath:dbPath error:nil]);
    NSError *failure = nil;
    require([store list:request error:&failure] == nil && [failure.domain isEqual:@"OMI_REWIND_UNAVAILABLE"]);
    require(sqlite3_open(dbPath.UTF8String, &db) == SQLITE_OK); sqlite3_close(db);
    failure = nil;
    require([store list:request error:&failure] == nil && [failure.domain isEqual:@"OMI_REWIND_STORAGE"]);
    NSData *invalid = [@"not a SQLite database" dataUsingEncoding:NSUTF8StringEncoding];
    require([invalid writeToFile:dbPath atomically:YES]);
    failure = nil;
    require([store list:request error:&failure] == nil && [failure.domain isEqual:@"OMI_REWIND_STORAGE"]);
    require([[NSData dataWithContentsOfFile:dbPath] isEqual:invalid]);
    require([NSFileManager.defaultManager removeItemAtPath:dbPath error:nil]);
    require([NSFileManager.defaultManager createDirectoryAtPath:dbPath withIntermediateDirectories:NO attributes:nil error:nil]);
    failure = nil;
    require([store list:request error:&failure] == nil && [failure.domain isEqual:@"OMI_REWIND_STORAGE"]);
    require([NSFileManager.defaultManager removeItemAtPath:root error:nil]);
    puts("Rewind read-only SQLite, missing versus unreadable storage, JPEG, exact HEVC samples, pagination, literal search, containment and owner-retirement tests passed");
  }
}
