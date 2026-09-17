#import "OmiDesktopCommandsModule.h"

#import <AppKit/AppKit.h>
#import <AVFoundation/AVFoundation.h>
#import <CoreGraphics/CoreGraphics.h>
#import <UserNotifications/UserNotifications.h>

NSString *const OmiDesktopSearchCommandNotification = @"OmiDesktopSearchCommandNotification";

static void OmiOpenPermissionSettings(NSString *pane, RCTPromiseResolveBlock resolve,
                                     RCTPromiseRejectBlock reject) {
  dispatch_async(dispatch_get_main_queue(), ^{
    NSURL *url = [NSURL URLWithString:[@"x-apple.systempreferences:" stringByAppendingString:pane]];
    if ([NSWorkspace.sharedWorkspace openURL:url]) {
      // Opening a pane is not a grant. React observes permissionStatus on return.
      resolve(@"denied");
    } else {
      reject(@"OMI_SETTINGS_UNAVAILABLE", @"Could not open System Settings", nil);
    }
  });
}

static NSString *OmiDesktopDefaultsKey(NSString *preference) {
  static NSDictionary<NSString *, NSString *> *keys;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    keys = @{
      @"softwarePlane" : @"omi.backend.softwarePlane",
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
      @"liveVoiceProvider" : @"omi.live.voiceProvider",
    };
  });
  return keys[preference];
}

static NSDictionary *OmiDesktopPreferenceSnapshot(void) {
  NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
  NSString *audioMode = [defaults stringForKey:@"audioRecordingMode"] ?: @"off";
  NSString *softwarePlane = [defaults stringForKey:@"omi.backend.softwarePlane"];
  NSString *liveVoiceProvider = [defaults stringForKey:@"omi.live.voiceProvider"] ?: @"gpt_live";
  NSString *stampedV5Origin = NSProcessInfo.processInfo.environment[@"OMI_V5_BACKEND_URL"];
  return @{
    @"softwarePlane" : softwarePlane ?: NSNull.null,
    @"stampedV5Origin" : stampedV5Origin ?: NSNull.null,
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
    @"liveVoiceProvider" : liveVoiceProvider,
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
    dispatch_async(dispatch_get_main_queue(), ^{
      if (CGPreflightScreenCaptureAccess() || CGRequestScreenCaptureAccess()) {
        resolve(@"granted");
      } else {
        OmiOpenPermissionSettings(@"com.apple.preference.security?Privacy_ScreenCapture", resolve, reject);
      }
    });
    return;
  }
  if ([kind isEqualToString:@"microphone"]) {
    AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio];
    if (status == AVAuthorizationStatusDenied || status == AVAuthorizationStatusRestricted) {
      OmiOpenPermissionSettings(@"com.apple.preference.security?Privacy_Microphone", resolve, reject);
      return;
    }
    [AVCaptureDevice requestAccessForMediaType:AVMediaTypeAudio completionHandler:^(BOOL granted) {
      resolve(granted ? @"granted" : @"denied");
    }];
    return;
  }
  if ([kind isEqualToString:@"notifications"]) {
    [UNUserNotificationCenter.currentNotificationCenter
        getNotificationSettingsWithCompletionHandler:^(UNNotificationSettings *settings) {
      if (settings.authorizationStatus == UNAuthorizationStatusDenied) {
        OmiOpenPermissionSettings(@"com.apple.preference.notifications", resolve, reject);
        return;
      }
      [UNUserNotificationCenter.currentNotificationCenter
          requestAuthorizationWithOptions:(UNAuthorizationOptionAlert | UNAuthorizationOptionSound |
                                           UNAuthorizationOptionBadge)
                        completionHandler:^(BOOL granted, NSError *error) {
        if (error) {
          reject(@"OMI_PERMISSION_FAILED", @"Could not request notifications", nil);
        } else {
          resolve(granted ? @"granted" : @"denied");
        }
      }];
    }];
    return;
  }
  reject(@"OMI_SETTINGS_INVALID", @"Unknown desktop permission", nil);
}

@end
