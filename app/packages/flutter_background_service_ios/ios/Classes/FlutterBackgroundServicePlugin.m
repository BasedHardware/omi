#import "FlutterBackgroundServicePlugin.h"
#if __has_include(<flutter_background_service_ios/flutter_background_service_ios-Swift.h>)
#import <flutter_background_service_ios/flutter_background_service_ios-Swift.h>
#else
// Support project import fallback if the generated compatibility header
// is not copied when this plugin is created as a library.
// https://forums.swift.org/t/swift-static-libraries-dont-copy-generated-objective-c-header/19816
#import "flutter_background_service_ios-Swift.h"
#endif

@interface GeneratedPluginRegistrant : NSObject
+ (void)registerWithRegistry:(NSObject<FlutterPluginRegistry>*)registry;
@end


@implementation FlutterBackgroundServicePlugin
+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar>*)registrar {
  [SwiftFlutterBackgroundServicePlugin registerWithRegistrar:registrar];
}

+ (void)setPluginRegistrantCallback:(FlutterPluginRegistrantCallback)callback {
    [SwiftFlutterBackgroundServicePlugin setPluginRegistrantCallback:callback];
}

+ (nullable Class)lookupGeneratedPluginRegistrant {
    NSString* classNameToCompare = @"GeneratedPluginRegistrant";
    return NSClassFromString(classNameToCompare);
}

+ (void)registerEngine:(FlutterEngine*)engine {
    [[FlutterBackgroundServicePlugin lookupGeneratedPluginRegistrant] registerWithRegistry:engine];
}
@end
