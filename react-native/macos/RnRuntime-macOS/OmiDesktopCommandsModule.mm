#import "OmiDesktopCommandsModule.h"

#import <AVFoundation/AVFoundation.h>
#import <CoreGraphics/CoreGraphics.h>
#import <UserNotifications/UserNotifications.h>

NSString *const OmiDesktopSearchCommandNotification = @"OmiDesktopSearchCommandNotification";

static NSString *OmiDesktopDefaultsKey(NSString *preference) {
  static NSDictionary<NSString *, NSString *> *keys;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    keys = @{
      @"screenCapture" : @"screenAnalysisEnabled",
      @"audioMode" : @"audioRecordingMode",
      @"interfaceSounds" : @"omi.sound.effectsEnabled",
      @"fontScale" : @"fontScale",
      @"notificationsEnabled" : @"notifications_enabled",
      @"rewindRetentionDays" : @"rewindRetentionDays",
      @"meetingNoteScreenshots" : @"meetingNoteScreenshotsEnabled",
      @"floatingBar" : @"askOmiBarEnabled",
      @"transcriptionAutoDetect" : @"transcriptionAutoDetect",
      @"vadGate" : @"vadGateEnabled",
      @"openOmiShortcut" : @"shortcut_askOmiEnabled",
      @"pushToTalk" : @"shortcut_pttEnabled",
    };
  });
  return keys[preference];
}

static NSDictionary *OmiDesktopPreferenceSnapshot(void) {
  NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
  NSString *audioMode = [defaults stringForKey:@"audioRecordingMode"] ?: @"off";
  return @{
    @"screenCapture" : @([defaults boolForKey:@"screenAnalysisEnabled"]),
    @"audioMode" : audioMode,
    @"interfaceSounds" : @([defaults objectForKey:@"omi.sound.effectsEnabled"] == nil
        ? YES : [defaults boolForKey:@"omi.sound.effectsEnabled"]),
    @"fontScale" : @([defaults objectForKey:@"fontScale"] == nil ? 100 : [defaults integerForKey:@"fontScale"]),
    @"notificationsEnabled" : @([defaults boolForKey:@"notifications_enabled"]),
    @"rewindRetentionDays" : @(
        [defaults objectForKey:@"rewindRetentionDays"] == nil ? 14 : [defaults integerForKey:@"rewindRetentionDays"]),
    @"meetingNoteScreenshots" : @([defaults objectForKey:@"meetingNoteScreenshotsEnabled"] == nil
        ? YES : [defaults boolForKey:@"meetingNoteScreenshotsEnabled"]),
    @"floatingBar" : @([defaults objectForKey:@"askOmiBarEnabled"] == nil
        ? YES : [defaults boolForKey:@"askOmiBarEnabled"]),
    @"transcriptionAutoDetect" : @([defaults objectForKey:@"transcriptionAutoDetect"] == nil
        ? YES : [defaults boolForKey:@"transcriptionAutoDetect"]),
    @"vadGate" : @([defaults objectForKey:@"vadGateEnabled"] == nil ? YES : [defaults boolForKey:@"vadGateEnabled"]),
    @"openOmiShortcut" : @([defaults objectForKey:@"shortcut_askOmiEnabled"] == nil
        ? YES : [defaults boolForKey:@"shortcut_askOmiEnabled"]),
    @"pushToTalk" : @([defaults objectForKey:@"shortcut_pttEnabled"] == nil
        ? YES : [defaults boolForKey:@"shortcut_pttEnabled"]),
  };
}

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

RCT_REMAP_METHOD(loadDesktopPreferences,
                 loadDesktopPreferencesWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  resolve(OmiDesktopPreferenceSnapshot());
}

RCT_REMAP_METHOD(setDesktopPreference,
                 setDesktopPreference:(NSString *)key
                 value:(id)value
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  NSString *defaultsKey = OmiDesktopDefaultsKey(key);
  if (defaultsKey.length == 0) {
    reject(@"OMI_SETTINGS_INVALID", @"Unknown desktop preference", nil);
    return;
  }
  [NSUserDefaults.standardUserDefaults setObject:value forKey:defaultsKey];
  resolve(OmiDesktopPreferenceSnapshot());
}

RCT_REMAP_METHOD(permissionStatus,
                 permissionStatusWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  NSString *screen = CGPreflightScreenCaptureAccess() ? @"granted" : @"denied";
  AVAuthorizationStatus microphone = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio];
  NSString *mic = microphone == AVAuthorizationStatusAuthorized
      ? @"granted"
      : microphone == AVAuthorizationStatusDenied || microphone == AVAuthorizationStatusRestricted
      ? @"denied"
      : @"unknown";
  [UNUserNotificationCenter.currentNotificationCenter getNotificationSettingsWithCompletionHandler:
      ^(UNNotificationSettings *settings) {
    NSString *notifications = settings.authorizationStatus == UNAuthorizationStatusAuthorized
        ? @"granted"
        : settings.authorizationStatus == UNAuthorizationStatusDenied ? @"denied" : @"unknown";
    resolve(@{
      @"screen" : screen,
      @"microphone" : mic,
      @"notifications" : notifications,
    });
  }];
}

RCT_REMAP_METHOD(requestPermission,
                 requestPermission:(NSString *)kind
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  if ([kind isEqualToString:@"screen"]) {
    BOOL granted = CGRequestScreenCaptureAccess();
    resolve(granted ? @"granted" : @"denied");
    return;
  }
  if ([kind isEqualToString:@"microphone"]) {
    [AVCaptureDevice requestAccessForMediaType:AVMediaTypeAudio completionHandler:^(BOOL granted) {
      resolve(granted ? @"granted" : @"denied");
    }];
    return;
  }
  if ([kind isEqualToString:@"notifications"]) {
    [UNUserNotificationCenter.currentNotificationCenter
        requestAuthorizationWithOptions:(UNAuthorizationOptionAlert | UNAuthorizationOptionSound |
                                         UNAuthorizationOptionBadge)
                      completionHandler:^(BOOL granted, NSError *__unused error) {
      resolve(granted ? @"granted" : @"denied");
    }];
    return;
  }
  reject(@"OMI_SETTINGS_INVALID", @"Unknown desktop permission", nil);
}

@end
