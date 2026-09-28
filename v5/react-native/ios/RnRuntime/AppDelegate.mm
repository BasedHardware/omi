#import "AppDelegate.h"

#import <React/RCTBundleURLProvider.h>
#import <ReactAppDependencyProvider/RCTAppDependencyProvider.h>

@interface OmiSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property (nonatomic, strong) UIWindow *window;
@end

@implementation OmiSceneDelegate

- (void)scene:(UIScene *)scene
    willConnectToSession:(UISceneSession *)session
                 options:(UISceneConnectionOptions *)connectionOptions
{
  if (![scene isKindOfClass:UIWindowScene.class]) {
    return;
  }

  AppDelegate *appDelegate = (AppDelegate *)UIApplication.sharedApplication.delegate;
  UIView *rootView = [appDelegate.rootViewFactory viewWithModuleName:appDelegate.moduleName
                                                  initialProperties:appDelegate.initialProps
                                                      launchOptions:nil];
  UIViewController *rootViewController = [UIViewController new];
  rootViewController.view = rootView;

  self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
  self.window.rootViewController = rootViewController;
  [self.window makeKeyAndVisible];
}

@end

@implementation AppDelegate

- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)launchOptions
{
  self.moduleName = @"RnRuntime";
  self.dependencyProvider = [RCTAppDependencyProvider new];
  self.automaticallyLoadReactNativeWindow = NO;

  NSSet<NSString *> *allowedRoutes = [NSSet setWithArray:@[
    @"Home",
    @"Chat",
    @"Conversations",
    @"Memories",
    @"Tasks",
  ]];
  NSString *requestedRoute = NSProcessInfo.processInfo.environment[@"OMI_INITIAL_ROUTE"];
  NSString *initialRoute = [allowedRoutes containsObject:requestedRoute] ? requestedRoute : @"Home";
  NSString *metroPort = NSProcessInfo.processInfo.environment[@"OMI_METRO_PORT"];
  if (metroPort.integerValue > 0 && metroPort.integerValue <= 65535) {
    [RCTBundleURLProvider sharedSettings].jsLocation = [NSString stringWithFormat:@"localhost:%@", metroPort];
  }
  self.initialProps = @{ @"initialRoute" : initialRoute };

  return [super application:application didFinishLaunchingWithOptions:launchOptions];
}

- (UISceneConfiguration *)application:(UIApplication *)application
    configurationForConnectingSceneSession:(UISceneSession *)connectingSceneSession
                                   options:(UISceneConnectionOptions *)options
{
  UISceneConfiguration *configuration =
      [[UISceneConfiguration alloc] initWithName:@"Default Configuration"
                                     sessionRole:connectingSceneSession.role];
  configuration.delegateClass = OmiSceneDelegate.class;
  return configuration;
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
