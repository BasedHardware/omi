#import "AppDelegate.h"
#import "OmiDesktopCommandsModule.h"

#import <React/RCTBundleURLProvider.h>
#import <ReactAppDependencyProvider/RCTAppDependencyProvider.h>

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
  self.moduleName = @"RnRuntime";
  // You can add your custom initial props in the dictionary below.
  // They will be passed down to the ViewController used by React Native.
  self.initialProps = @{};
  self.dependencyProvider = [RCTAppDependencyProvider new];

  [super applicationDidFinishLaunching:notification];
  [self installDesktopSearchCommand];
}

- (void)installDesktopSearchCommand
{
  NSMenu *mainMenu = NSApplication.sharedApplication.mainMenu;
  NSMenuItem *editItem = [mainMenu itemWithTitle:@"Edit"];
  NSMenu *editMenu = editItem.submenu;
  if (editMenu == nil) {
    editItem = [[NSMenuItem alloc] initWithTitle:@"Edit" action:nil keyEquivalent:@""];
    editMenu = [[NSMenu alloc] initWithTitle:@"Edit"];
    editItem.submenu = editMenu;
    [mainMenu addItem:editItem];
  }
  NSMenuItem *searchItem = [[NSMenuItem alloc] initWithTitle:@"Search"
                                                      action:@selector(focusOmiSearch:)
                                               keyEquivalent:@"k"];
  searchItem.keyEquivalentModifierMask = NSEventModifierFlagCommand;
  searchItem.target = self;
  [editMenu addItem:searchItem];
}

- (void)focusOmiSearch:(id)sender
{
  [NSNotificationCenter.defaultCenter postNotificationName:OmiDesktopSearchCommandNotification
                                                      object:nil];
}

- (NSURL *)sourceURLForBridge:(RCTBridge *)bridge
{
  return [self bundleURL];
}

- (NSURL *)bundleURL
{
#if DEBUG
  return [[RCTBundleURLProvider sharedSettings] jsBundleURLForBundleRoot:@"index"];
#else
  return [[NSBundle mainBundle] URLForResource:@"main" withExtension:@"jsbundle"];
#endif
}

/// This method controls whether the `concurrentRoot`feature of React18 is turned on or off.
///
/// @see: https://reactjs.org/blog/2022/03/29/react-v18.html
/// @note: This requires to be rendering on Fabric (i.e. on the New Architecture).
/// @return: `true` if the `concurrentRoot` feature is enabled. Otherwise, it returns `false`.
- (BOOL)concurrentRootEnabled
{
#ifdef RN_FABRIC_ENABLED
  return true;
#else
  return false;
#endif
}

@end
