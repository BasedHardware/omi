#import "AppDelegate.h"

#import <React/RCTBundleURLProvider.h>
#import <ReactAppDependencyProvider/RCTAppDependencyProvider.h>

@implementation AppDelegate

- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)launchOptions
{
  self.moduleName = @"RnRuntime";
  self.dependencyProvider = [RCTAppDependencyProvider new];

  NSSet<NSString *> *allowedRoutes = [NSSet setWithArray:@[
    @"Home",
    @"Chat",
    @"Conversations",
    @"Memories",
    @"Tasks",
  ]];
  NSString *requestedRoute = NSProcessInfo.processInfo.environment[@"OMI_INITIAL_ROUTE"];
  NSString *initialRoute = [allowedRoutes containsObject:requestedRoute] ? requestedRoute : @"Home";
  self.initialProps = @{ @"initialRoute" : initialRoute };

  return [super application:application didFinishLaunchingWithOptions:launchOptions];
}

- (NSURL *)bundleURL
{
#if DEBUG
  return [[RCTBundleURLProvider sharedSettings] jsBundleURLForBundleRoot:@"index"];
#else
  return [NSBundle.mainBundle URLForResource:@"main" withExtension:@"jsbundle"];
#endif
}

@end
