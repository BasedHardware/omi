#import "OmiDesktopCommandsModule.h"

NSString *const OmiDesktopSearchCommandNotification = @"OmiDesktopSearchCommandNotification";

@interface OmiDesktopCommandsModule ()
@property(nonatomic) BOOL observing;
@end

@implementation OmiDesktopCommandsModule

RCT_EXPORT_MODULE(OmiDesktopCommands)

+ (BOOL)requiresMainQueueSetup
{
  return YES;
}

- (NSArray<NSString *> *)supportedEvents
{
  return @[ @"desktopSearchCommand" ];
}

- (void)startObserving
{
  self.observing = YES;
  [NSNotificationCenter.defaultCenter addObserver:self
                                         selector:@selector(receiveSearchCommand:)
                                             name:OmiDesktopSearchCommandNotification
                                           object:nil];
}

- (void)stopObserving
{
  self.observing = NO;
  [NSNotificationCenter.defaultCenter removeObserver:self
                                                name:OmiDesktopSearchCommandNotification
                                              object:nil];
}

- (void)receiveSearchCommand:(NSNotification *)notification
{
  if (self.observing) {
    [self sendEventWithName:@"desktopSearchCommand" body:@{}];
  }
}

@end
