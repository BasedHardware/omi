#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface ObjCExceptionCatcher : NSObject

/// Executes the given block and catches any ObjC NSException.
/// Returns the exception if one was thrown, or nil on success.
+ (nullable NSException *)catchException:(void (NS_NOESCAPE ^)(void))block NS_SWIFT_NAME(catching(_:));

@end

NS_ASSUME_NONNULL_END
