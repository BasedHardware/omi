#import "OmiRewindCapture.h"
#import <AppKit/AppKit.h>
#import <sqlite3.h>
#import <fcntl.h>
#import <unistd.h>
#import <assert.h>

@interface FastCapture : OmiRewindCapture
@end
@implementation FastCapture
- (NSTimeInterval)captureTimeout { return 0.03; }
@end

static void Wait(dispatch_semaphore_t semaphore) {
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:20];
  while (dispatch_semaphore_wait(semaphore, DISPATCH_TIME_NOW) != 0) {
    assert(deadline.timeIntervalSinceNow > 0);
    [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.005]];
  }
}
static NSInteger Rows(NSURL *root, NSString *uid) {
  sqlite3 *db = nullptr;
  NSURL *path = [[[root URLByAppendingPathComponent:@"users"] URLByAppendingPathComponent:uid] URLByAppendingPathComponent:@"omi.db"];
  if (sqlite3_open_v2(path.path.UTF8String, &db, SQLITE_OPEN_READONLY, nullptr) != SQLITE_OK) { if (db) sqlite3_close(db); return 0; }
  sqlite3_stmt *statement = nullptr;
  assert(sqlite3_prepare_v2(db, "SELECT count(*) FROM screenshots", -1, &statement, nullptr) == SQLITE_OK);
  assert(sqlite3_step(statement) == SQLITE_ROW);
  NSInteger count = sqlite3_column_int(statement, 0);
  sqlite3_finalize(statement);
  if (count > 0) {
    assert(sqlite3_prepare_v2(db, "SELECT ocrText FROM screenshots LIMIT 1", -1, &statement, nullptr) == SQLITE_OK);
    assert(sqlite3_step(statement) == SQLITE_ROW);
    NSString *text = [NSString stringWithUTF8String:(const char *)sqlite3_column_text(statement, 0)];
    assert([text containsString:@"REWIND"] && [text containsString:@"FIXTURE"]);
    sqlite3_finalize(statement);
  }
  sqlite3_close(db); return count;
}
int main() {
  @autoreleasepool {
    NSURL *root = [[NSURL fileURLWithPath:@"/private/tmp"] URLByAppendingPathComponent:[@"omi-capture-test-" stringByAppendingString:NSUUID.UUID.UUIDString]];
    __block NSDictionary *identity = @{@"uid":@"fixture-user", @"login":@"first"};
    CGColorSpaceRef colors = CGColorSpaceCreateDeviceRGB();
    CGContextRef context = CGBitmapContextCreate(nullptr, 640, 160, 8, 640 * 4, colors, kCGImageAlphaPremultipliedLast);
    CGContextSetRGBFillColor(context, 1, 1, 1, 1); CGContextFillRect(context, CGRectMake(0,0,640,160));
    [NSGraphicsContext saveGraphicsState];
    NSGraphicsContext.currentContext = [NSGraphicsContext graphicsContextWithCGContext:context flipped:NO];
    [@"REWIND FIXTURE" drawAtPoint:NSMakePoint(20,60) withAttributes:@{NSFontAttributeName:[NSFont systemFontOfSize:40], NSForegroundColorAttributeName:NSColor.blackColor}];
    [NSGraphicsContext restoreGraphicsState];
    CGImageRef image = CGBitmapContextCreateImage(context);
    CGContextRelease(context); CGColorSpaceRelease(colors);
    __block void (^pending)(CGImageRef, NSString *, NSString *, NSError *);
    OmiRewindFrameSource source = ^(void (^completion)(CGImageRef, NSString *, NSString *, NSError *)) { pending = completion; };
    OmiRewindCapture *capture = [[OmiRewindCapture alloc] initWithIdentity:^NSDictionary *{ return identity; } root:root source:source permission:^BOOL {return YES;}];
    NSError *error = nil;
    assert([capture startCapture:&error]);
    dispatch_semaphore_t saved = dispatch_semaphore_create(0);
    [capture captureFrame:^(NSDictionary *value, NSError *failure) { if (failure) fprintf(stderr, "synthetic capture error: %s\n", failure.domain.UTF8String); assert(failure == nil && [value[@"captured"] boolValue]); dispatch_semaphore_signal(saved); }];
    pending(image, @"Fixture Editor", @"Synthetic", nil); Wait(saved);
    assert(Rows(root, @"fixture-user") == 1);
    for (NSString *mode in @[@"excluded", @"stop", @"account", @"lock"]) {
      identity = @{@"uid":@"fixture-user", @"login":@"first"};
      assert([capture startCapture:&error]);
      dispatch_semaphore_t done = dispatch_semaphore_create(0);
      [capture captureFrame:^(NSDictionary *value, NSError *failure) {
        assert([mode isEqual:@"excluded"] ? failure == nil && ![value[@"captured"] boolValue] : failure != nil);
        dispatch_semaphore_signal(done);
      }];
      if ([mode isEqual:@"stop"]) [capture stopCapture];
      if ([mode isEqual:@"account"]) identity = @{@"uid":@"fixture-next", @"login":@"next"};
      if ([mode isEqual:@"lock"]) [NSWorkspace.sharedWorkspace.notificationCenter postNotificationName:NSWorkspaceSessionDidResignActiveNotification object:nil];
      pending(image, [mode isEqual:@"excluded"] ? @"1Password" : @"Fixture Editor", nil, nil); Wait(done);
      assert(Rows(root, @"fixture-user") == 1 && Rows(root, @"fixture-next") == 0);
    }
    [capture invalidate];
    assert(![capture startCapture:&error]);
    identity = @{@"uid":@"fixture-user", @"login":@"first"};
    FastCapture *fast = [[FastCapture alloc] initWithIdentity:^NSDictionary *{return identity;} root:root source:source permission:^BOOL{return YES;}];
    assert([fast startCapture:&error]);
    dispatch_semaphore_t timed = dispatch_semaphore_create(0);
    [fast captureFrame:^(NSDictionary *value, NSError *failure) { assert([failure.domain isEqual:@"OMI_CAPTURE_TIMEOUT"]); dispatch_semaphore_signal(timed); }];
    void (^old)(CGImageRef, NSString *, NSString *, NSError *) = pending;
    Wait(timed);
    assert([fast startCapture:&error]);
    dispatch_semaphore_t second = dispatch_semaphore_create(0);
    [fast captureFrame:^(NSDictionary *value, NSError *failure) { assert(failure == nil && ![value[@"captured"] boolValue]); dispatch_semaphore_signal(second); }];
    old(image, @"Fixture Editor", nil, nil);
    pending(nil, @"1Password", nil, nil); Wait(second);
    assert(Rows(root, @"fixture-user") == 1);
    [fast invalidate];
    CGImageRelease(image);
    assert([NSFileManager.defaultManager removeItemAtURL:root error:nil]);
    puts("Omi Rewind capture: synthetic JPEG/OCR persistence, exclusion, stop, account, lock, timeout and late-frame fences passed");
  }
}
