#import <Flutter/Flutter.h>

@interface FlutterBackgroundServicePlugin : NSObject<FlutterPlugin>
+ (void)registerEngine:(FlutterEngine*)engine;
@end
