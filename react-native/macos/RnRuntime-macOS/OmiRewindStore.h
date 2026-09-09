#import <Foundation/Foundation.h>
#import <AVFoundation/AVFoundation.h>
#import <CoreImage/CoreImage.h>
#import <ImageIO/ImageIO.h>
#import <CommonCrypto/CommonDigest.h>
#import <sqlite3.h>
#import <sys/stat.h>
#import <fcntl.h>
#import <unistd.h>
#import <errno.h>

static NSError *OmiRewindError(NSString *code) { return [NSError errorWithDomain:code code:1 userInfo:nil]; }
static NSString *OmiRewindOwner(NSDictionary *identity) {
  NSData *bytes = [[NSString stringWithFormat:@"%@:%@", identity[@"uid"], identity[@"login"]] dataUsingEncoding:NSUTF8StringEncoding];
  unsigned char digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(bytes.bytes, (CC_LONG)bytes.length, digest);
  NSMutableString *value = [NSMutableString string]; for (NSUInteger i = 0; i < sizeof(digest); i++) [value appendFormat:@"%02x", digest[i]];
  return value;
}
static NSString *OmiRewindText(sqlite3_stmt *statement, int index) {
  const unsigned char *value = sqlite3_column_text(statement, index);
  return value == NULL ? @"" : [[NSString alloc] initWithBytes:value length:sqlite3_column_bytes(statement, index) encoding:NSUTF8StringEncoding];
}
static NSString *OmiRewindContained(NSString *root, NSString *relative) {
  if (relative.length == 0 || relative.length > 1024 || relative.isAbsolutePath || [relative.pathComponents containsObject:@".."] || [relative rangeOfString:@"\0"].location != NSNotFound) return nil;
  NSString *base = root.stringByResolvingSymlinksInPath.stringByStandardizingPath;
  if (![base isEqual:root.stringByStandardizingPath]) return nil;
  NSString *path = [root stringByAppendingPathComponent:relative].stringByResolvingSymlinksInPath.stringByStandardizingPath;
  return [path hasPrefix:[base stringByAppendingString:@"/"]] ? path : nil;
}
@interface OmiRewindStore : NSObject
@property(nonatomic, copy) NSString *root;
@property(nonatomic, copy) NSDictionary *(^identity)(void);
@property(atomic) BOOL disposed;
- (instancetype)initWithRoot:(NSString *)root identity:(NSDictionary *(^)(void))identity;
- (NSDictionary *)list:(NSDictionary *)input error:(NSError **)error;
- (NSDictionary *)read:(NSString *)identifier error:(NSError **)error;
@end
@implementation OmiRewindStore
- (instancetype)initWithRoot:(NSString *)root identity:(NSDictionary *(^)(void))identity { if ((self = [super init])) { _root = root; _identity = [identity copy]; } return self; }
- (BOOL)current:(NSDictionary *)owner { return !self.disposed && owner != nil && [owner isEqual:self.identity()]; }
- (sqlite3 *)open:(NSDictionary *)owner error:(NSError **)error {
  if (owner == nil) { if (error) *error = OmiRewindError(@"OMI_REWIND_AUTH"); return NULL; }
  if (![self current:owner]) { if (error) *error = OmiRewindError(@"OMI_REWIND_OWNER_CHANGED"); return NULL; }
  NSString *uid = owner[@"uid"];
  NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:@"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"];
  if (![uid isKindOfClass:NSString.class] || uid.length == 0 || uid.length > 128 || [uid rangeOfCharacterFromSet:allowed.invertedSet].location != NSNotFound) { if (error) *error = OmiRewindError(@"OMI_REWIND_STORAGE"); return NULL; }
  NSString *path = OmiRewindContained(self.root, [NSString stringWithFormat:@"%@/omi.db", uid]);
  NSString *expected = [[self.root stringByAppendingPathComponent:uid] stringByAppendingPathComponent:@"omi.db"];
  if (path == nil || ![path isEqual:expected.stringByStandardizingPath]) { if (error) *error = OmiRewindError(@"OMI_REWIND_STORAGE"); return NULL; }
  // Only a confirmed missing database means there is no history. Existing but
  // unreadable storage must not become an empty successful timeline.
  struct stat attributes = {};
  if (lstat(path.fileSystemRepresentation, &attributes) != 0) { if (error) *error = OmiRewindError(errno == ENOENT ? @"OMI_REWIND_UNAVAILABLE" : @"OMI_REWIND_STORAGE"); return NULL; }
  if (!S_ISREG(attributes.st_mode)) { if (error) *error = OmiRewindError(@"OMI_REWIND_STORAGE"); return NULL; }
  sqlite3 *db = NULL;
  if (sqlite3_open_v2(path.fileSystemRepresentation, &db, SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX | SQLITE_OPEN_NOFOLLOW, NULL) != SQLITE_OK) { if (db) sqlite3_close(db); if (error) *error = OmiRewindError(@"OMI_REWIND_STORAGE"); return NULL; }
  sqlite3_busy_timeout(db, 500);
  sqlite3_exec(db, "PRAGMA query_only=ON; PRAGMA trusted_schema=OFF", NULL, NULL, NULL);
  return db;
}
- (NSDictionary *)list:(NSDictionary *)input error:(NSError **)error {
  NSDictionary *owner = self.identity();
  NSString *query = input[@"query"];
  NSNumber *limit = input[@"limit"];
  id cursor = input[@"cursor"];
  if (![query isKindOfClass:NSString.class] || query.length > 200 || ![limit isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)limit) == CFBooleanGetTypeID() || limit.doubleValue != limit.integerValue || limit.integerValue < 1 || limit.integerValue > 50 || (cursor != nil && cursor != NSNull.null && ![cursor isKindOfClass:NSString.class])) { if (error) *error = OmiRewindError(@"OMI_REWIND_INVALID_REQUEST"); return nil; }
  NSString *ownerKey = OmiRewindOwner(owner);
  NSString *before = @"9999-12-31 23:59:59.999"; long long beforeId = LLONG_MAX;
  if ([cursor isKindOfClass:NSString.class]) {
    if ([cursor length] > 4096) { if (error) *error = OmiRewindError(@"OMI_REWIND_INVALID_REQUEST"); return nil; }
    NSData *bytes = [[NSData alloc] initWithBase64EncodedString:cursor options:0];
    id parsed = bytes == nil ? nil : [NSJSONSerialization JSONObjectWithData:bytes options:0 error:nil];
    if (![parsed isKindOfClass:NSDictionary.class] || ![parsed[@"owner"] isEqual:ownerKey] || ![parsed[@"query"] isEqual:query] || ![parsed[@"timestamp"] isKindOfClass:NSString.class] || [parsed[@"timestamp"] length] > 32 || ![parsed[@"id"] isKindOfClass:NSString.class]) { if (error) *error = OmiRewindError(@"OMI_REWIND_STALE_CURSOR"); return nil; }
    before = parsed[@"timestamp"]; beforeId = [parsed[@"id"] longLongValue];
    if (beforeId <= 0 || ![[NSString stringWithFormat:@"%lld", beforeId] isEqual:parsed[@"id"]]) { if (error) *error = OmiRewindError(@"OMI_REWIND_STALE_CURSOR"); return nil; }
  }
  sqlite3 *db = [self open:owner error:error]; if (db == NULL) return nil;
  CFTimeInterval deadline = CFAbsoluteTimeGetCurrent() + 2;
  sqlite3_progress_handler(db, 1000, [](void *value) -> int { return CFAbsoluteTimeGetCurrent() > *(CFTimeInterval *)value; }, &deadline);
  sqlite3_stmt *statement = NULL;
  const char *sql = "SELECT id,timestamp,substr(appName,1,256),substr(coalesce(windowTitle,''),1,1024),CAST(round((julianday(timestamp)-2440587.5)*86400000) AS INTEGER) FROM screenshots WHERE (timestamp<?1 OR (timestamp=?1 AND id<?2)) AND (?3='' OR instr(lower(appName),lower(?3))>0 OR instr(lower(windowTitle),lower(?3))>0 OR instr(lower(ocrText),lower(?3))>0) ORDER BY timestamp DESC,id DESC LIMIT ?4";
  NSMutableArray *rows = [NSMutableArray array]; NSDictionary *next = nil; int status = SQLITE_ERROR;
  if (sqlite3_prepare_v2(db, sql, -1, &statement, NULL) == SQLITE_OK) {
    sqlite3_bind_text(statement, 1, before.UTF8String, -1, SQLITE_TRANSIENT); sqlite3_bind_int64(statement, 2, beforeId); sqlite3_bind_text(statement, 3, query.UTF8String, -1, SQLITE_TRANSIENT); sqlite3_bind_int(statement, 4, limit.intValue + 1);
    while ((status = sqlite3_step(statement)) == SQLITE_ROW) {
      if (rows.count == limit.unsignedIntegerValue) break;
      NSString *rowId = [NSString stringWithFormat:@"%lld", sqlite3_column_int64(statement, 0)];
      NSString *timestamp = OmiRewindText(statement, 1), *app = OmiRewindText(statement, 2), *title = OmiRewindText(statement, 3);
      long long captured = sqlite3_column_int64(statement, 4);
      if (timestamp == nil || app == nil || title == nil || sqlite3_column_type(statement, 4) == SQLITE_NULL || captured < 0) { status = SQLITE_ERROR; break; }
      [rows addObject:@{@"id":[NSString stringWithFormat:@"%@:%@", ownerKey,rowId], @"capturedAtMs":@(captured), @"appName":app, @"windowTitle":title}];
      next = @{@"owner":ownerKey,@"query":query,@"timestamp":timestamp,@"id":rowId};
    }
  }
  if (statement) sqlite3_finalize(statement); sqlite3_close(db);
  if (![self current:owner]) { if (error) *error = OmiRewindError(@"OMI_REWIND_OWNER_CHANGED"); return nil; }
  if (status != SQLITE_DONE && status != SQLITE_ROW) { if (error) *error = OmiRewindError(@"OMI_REWIND_STORAGE"); return nil; }
  NSString *nextCursor = status == SQLITE_ROW && next != nil ? [[NSJSONSerialization dataWithJSONObject:next options:0 error:nil] base64EncodedStringWithOptions:0] : nil;
  return @{@"frames":rows,@"nextCursor":nextCursor ?: NSNull.null};
}
- (NSDictionary *)read:(NSString *)identifier error:(NSError **)error {
  NSDictionary *owner = self.identity();
  NSString *prefix = [OmiRewindOwner(owner) stringByAppendingString:@":"];
  if (![identifier isKindOfClass:NSString.class] || identifier.length > 100 || ![identifier hasPrefix:prefix]) { if (error) *error = OmiRewindError(@"OMI_REWIND_OWNER_CHANGED"); return nil; }
  NSString *rowId = [identifier substringFromIndex:prefix.length];
  if (rowId.length == 0 || rowId.length > 19 || [rowId rangeOfCharacterFromSet:NSCharacterSet.decimalDigitCharacterSet.invertedSet].location != NSNotFound || rowId.longLongValue <= 0 || ![[NSString stringWithFormat:@"%lld", rowId.longLongValue] isEqual:rowId]) { if (error) *error = OmiRewindError(@"OMI_REWIND_INVALID_REQUEST"); return nil; }
  sqlite3 *db = [self open:owner error:error]; if (db == NULL) return nil;
  sqlite3_stmt *statement = NULL; NSString *imagePath = nil, *videoPath = nil; long long offset = -1;
  if (sqlite3_prepare_v2(db, "SELECT imagePath,videoChunkPath,frameOffset FROM screenshots WHERE id=?1", -1, &statement, NULL) == SQLITE_OK) {
    sqlite3_bind_int64(statement, 1, rowId.longLongValue);
    if (sqlite3_step(statement) == SQLITE_ROW) {
      imagePath = OmiRewindText(statement, 0); videoPath = OmiRewindText(statement, 1);
      if (sqlite3_column_type(statement, 2) != SQLITE_NULL) offset = sqlite3_column_int64(statement, 2);
    }
  }
  if (statement) sqlite3_finalize(statement); sqlite3_close(db);
  NSString *ownerRoot = [self.root stringByAppendingPathComponent:owner[@"uid"]];
  CGImageRef image = NULL;
  if (imagePath.length > 0) {
    NSString *path = OmiRewindContained([ownerRoot stringByAppendingPathComponent:@"Screenshots"], imagePath);
    int file = path == nil ? -1 : open(path.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW);
    struct stat statbuf = {};
    if (file >= 0 && fstat(file, &statbuf) == 0 && S_ISREG(statbuf.st_mode) && statbuf.st_size > 0 && statbuf.st_size <= 10 * 1024 * 1024) {
      NSMutableData *data = [NSMutableData dataWithLength:(NSUInteger)statbuf.st_size]; size_t total = 0;
      while (total < data.length) { ssize_t count = pread(file, (char *)data.mutableBytes + total, data.length - total, total); if (count <= 0) break; total += count; }
      if (total == data.length) {
        CGImageSourceRef source = CGImageSourceCreateWithData((__bridge CFDataRef)data, NULL);
        if (source) {
          NSDictionary *properties = CFBridgingRelease(CGImageSourceCopyPropertiesAtIndex(source, 0, NULL));
          double width = [properties[(__bridge id)kCGImagePropertyPixelWidth] doubleValue], height = [properties[(__bridge id)kCGImagePropertyPixelHeight] doubleValue];
          if (width > 0 && height > 0 && width * height <= 20000000) image = CGImageSourceCreateThumbnailAtIndex(source, 0, (__bridge CFDictionaryRef)@{(__bridge id)kCGImageSourceCreateThumbnailFromImageAlways:@YES,(__bridge id)kCGImageSourceThumbnailMaxPixelSize:@1600,(__bridge id)kCGImageSourceCreateThumbnailWithTransform:@YES});
          CFRelease(source);
        }
      }
    }
    if (file >= 0) close(file);
  }
  if (image == NULL && videoPath.length > 0 && offset >= 0 && offset < 10000) {
    NSString *path = OmiRewindContained([ownerRoot stringByAppendingPathComponent:@"Videos"], videoPath);
    NSDictionary *attributes = path == nil ? nil : [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
    if ([attributes[NSFileType] isEqual:NSFileTypeRegular] && [attributes[NSFileSize] unsignedLongLongValue] <= 512 * 1024 * 1024) {
      AVURLAsset *asset = [AVURLAsset URLAssetWithURL:[NSURL fileURLWithPath:path] options:nil];
      AVAssetTrack *track = [asset tracksWithMediaType:AVMediaTypeVideo].firstObject;
      CGSize size = track.naturalSize;
      if (track != nil && size.width > 0 && size.height > 0 && size.width * size.height <= 20000000) {
        AVAssetReader *reader = [[AVAssetReader alloc] initWithAsset:asset error:nil];
        AVAssetReaderTrackOutput *output = [[AVAssetReaderTrackOutput alloc] initWithTrack:track outputSettings:@{(__bridge id)kCVPixelBufferPixelFormatTypeKey:@(kCVPixelFormatType_32BGRA)}];
        output.alwaysCopiesSampleData = NO;
        if ([reader canAddOutput:output]) {
          [reader addOutput:output];
          if ([reader startReading]) {
            CFTimeInterval deadline = CFAbsoluteTimeGetCurrent() + 8;
            for (long long index = 0; index <= offset && [self current:owner] && CFAbsoluteTimeGetCurrent() < deadline; index++) {
              CMSampleBufferRef sample = [output copyNextSampleBuffer]; if (sample == NULL) break;
              if (index == offset) {
                CVImageBufferRef buffer = CMSampleBufferGetImageBuffer(sample);
                if (buffer) {
                  CIImage *frame = [CIImage imageWithCVPixelBuffer:buffer];
                  CGFloat scale = MIN(1, 1600 / MAX(frame.extent.size.width, frame.extent.size.height));
                  frame = [frame imageByApplyingTransform:CGAffineTransformMakeScale(scale, scale)];
                  image = [[CIContext contextWithOptions:nil] createCGImage:frame fromRect:frame.extent];
                }
              }
              CFRelease(sample);
            }
          }
          [reader cancelReading];
        }
      }
    }
  }
  if (image == NULL) { if (error) *error = OmiRewindError(@"OMI_REWIND_FRAME_UNAVAILABLE"); return nil; }
  NSMutableData *jpeg = [NSMutableData data];
  CGImageDestinationRef destination = CGImageDestinationCreateWithData((__bridge CFMutableDataRef)jpeg, CFSTR("public.jpeg"), 1, NULL);
  BOOL success = NO;
  if (destination) { CGImageDestinationAddImage(destination, image, (__bridge CFDictionaryRef)@{(__bridge id)kCGImageDestinationLossyCompressionQuality:@0.8}); success = CGImageDestinationFinalize(destination); CFRelease(destination); }
  CGImageRelease(image);
  if (![self current:owner]) { if (error) *error = OmiRewindError(@"OMI_REWIND_OWNER_CHANGED"); return nil; }
  if (!success || jpeg.length > 3 * 1024 * 1024) { if (error) *error = OmiRewindError(@"OMI_REWIND_FRAME_UNAVAILABLE"); return nil; }
  return @{@"id":identifier,@"mimeType":@"image/jpeg",@"base64":[jpeg base64EncodedStringWithOptions:0]};
}
@end
