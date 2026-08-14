#import "OmiNativeModule.h"

#import <AVFAudio/AVFAudio.h>
#import <CoreBluetooth/CoreBluetooth.h>
#import <UserNotifications/UserNotifications.h>

static NSString *const OmiServiceUUID = @"19b10000-e8f2-537e-4f6c-d104768a1214";

@interface OmiNativeModule () <CBCentralManagerDelegate, CBPeripheralDelegate>
@property(nonatomic, strong) CBCentralManager *central;
@property(nonatomic, strong) NSMutableDictionary<NSString *, CBPeripheral *> *peripherals;
@property(nonatomic, strong) NSMutableDictionary<NSString *, NSDictionary *> *devices;
@property(nonatomic, strong) CBPeripheral *connectedPeripheral;
@property(nonatomic, copy) NSString *connectionState;
@property(nonatomic, copy) NSString *lastEvent;
@property(nonatomic) BOOL scanning;
@end

@implementation OmiNativeModule

RCT_EXPORT_MODULE(OmiNative)

+ (BOOL)requiresMainQueueSetup {
  return YES;
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _peripherals = [NSMutableDictionary dictionary];
    _devices = [NSMutableDictionary dictionary];
    _connectionState = @"disconnected";
    _lastEvent = @"Bluetooth adapter not checked";
    _central = [[CBCentralManager alloc] initWithDelegate:self queue:dispatch_get_main_queue()];
  }
  return self;
}

RCT_REMAP_METHOD(getSnapshot,
                 getSnapshotWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  [[UNUserNotificationCenter currentNotificationCenter] getNotificationSettingsWithCompletionHandler:^(UNNotificationSettings *settings) {
    dispatch_async(dispatch_get_main_queue(), ^{
      resolve([self snapshotWithNotifications:settings.authorizationStatus]);
    });
  }];
}

RCT_REMAP_METHOD(getBluetoothState,
                 getBluetoothStateWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  resolve([self bluetoothState]);
}

RCT_REMAP_METHOD(requestPermissions,
                 requestPermissionsWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  [[AVAudioSession sharedInstance] requestRecordPermission:^(BOOL granted) {
    [[UNUserNotificationCenter currentNotificationCenter] requestAuthorizationWithOptions:(UNAuthorizationOptionAlert | UNAuthorizationOptionBadge | UNAuthorizationOptionSound)
                                                                        completionHandler:^(BOOL notificationGranted, NSError *error) {
      dispatch_async(dispatch_get_main_queue(), ^{
        resolve(@{
          @"microphone": granted ? @"granted" : @"denied",
          @"notifications": notificationGranted ? @"granted" : @"denied",
        });
      });
    }];
  }];
}

RCT_REMAP_METHOD(startScan,
                 startScanWithTimeout:(NSNumber *)timeoutSeconds
                 serviceUuids:(NSArray<NSString *> *)serviceUuids
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  if (self.central.state != CBManagerStatePoweredOn) {
    self.lastEvent = @"Bluetooth is not powered on";
    resolve(@[]);
    return;
  }
  NSMutableArray<CBUUID *> *uuids = [NSMutableArray array];
  for (NSString *uuid in serviceUuids.count ? serviceUuids : @[ OmiServiceUUID ]) {
    [uuids addObject:[CBUUID UUIDWithString:uuid]];
  }
  [self.devices removeAllObjects];
  [self.central scanForPeripheralsWithServices:uuids options:@{ CBCentralManagerScanOptionAllowDuplicatesKey: @NO }];
  self.scanning = YES;
  self.lastEvent = @"Scanning for Omi devices";
  resolve([self deviceList]);
}

RCT_REMAP_METHOD(stopScan,
                 stopScanWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  [self.central stopScan];
  self.scanning = NO;
  self.lastEvent = @"Omi scan stopped";
  resolve(nil);
}

RCT_REMAP_METHOD(connectDevice,
                 connectDeviceWithId:(NSString *)identifier
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  CBPeripheral *peripheral = self.peripherals[identifier];
  if (peripheral == nil) {
    reject(@"OMI_DEVICE_UNAVAILABLE", @"Omi device is unavailable", nil);
    return;
  }
  [self.central stopScan];
  self.scanning = NO;
  self.connectionState = @"connecting";
  self.connectedPeripheral = peripheral;
  [self.central connectPeripheral:peripheral options:nil];
  resolve(nil);
}

RCT_REMAP_METHOD(disconnectDevice,
                 disconnectDeviceWithId:(NSString *)identifier
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  if ([self.connectedPeripheral.identifier.UUIDString isEqualToString:identifier]) {
    [self.central cancelPeripheralConnection:self.connectedPeripheral];
  }
  resolve(nil);
}

- (void)centralManagerDidUpdateState:(CBCentralManager *)central {
  self.lastEvent = [NSString stringWithFormat:@"Bluetooth is %@", [self bluetoothState]];
}

- (void)centralManager:(CBCentralManager *)central
 didDiscoverPeripheral:(CBPeripheral *)peripheral
     advertisementData:(NSDictionary<NSString *, id> *)advertisementData
                  RSSI:(NSNumber *)RSSI {
  NSString *identifier = peripheral.identifier.UUIDString;
  self.peripherals[identifier] = peripheral;
  self.devices[identifier] = @{
    @"id": identifier,
    @"name": peripheral.name ?: advertisementData[CBAdvertisementDataLocalNameKey] ?: @"Omi",
    @"rssi": RSSI,
    @"connected": @NO,
  };
  self.lastEvent = [NSString stringWithFormat:@"Found %lu Omi device%@", (unsigned long)self.devices.count, self.devices.count == 1 ? @"" : @"s"];
}

- (void)centralManager:(CBCentralManager *)central didConnectPeripheral:(CBPeripheral *)peripheral {
  self.connectionState = @"connected";
  self.lastEvent = @"Connected to Omi";
}

- (void)centralManager:(CBCentralManager *)central
didFailToConnectPeripheral:(CBPeripheral *)peripheral
                 error:(NSError *)error {
  self.connectionState = @"disconnected";
  self.lastEvent = error.localizedDescription ?: @"Omi connection failed";
}

- (void)centralManager:(CBCentralManager *)central
didDisconnectPeripheral:(CBPeripheral *)peripheral
                 error:(NSError *)error {
  self.connectionState = @"disconnected";
  self.connectedPeripheral = nil;
  self.lastEvent = error.localizedDescription ?: @"Disconnected from Omi";
}

- (NSDictionary *)snapshotWithNotifications:(UNAuthorizationStatus)notificationStatus {
  return @{
    @"bluetooth": [self bluetoothState],
    @"devices": [self deviceList],
    @"capture": @"idle",
    @"captureMode": @"stream",
    @"microphone": [self microphoneState],
    @"notifications": notificationStatus == UNAuthorizationStatusAuthorized ? @"granted" : @"denied",
    @"background": @"inactive",
    @"audioRoute": @"phone-mic",
    @"lastEvent": self.lastEvent,
  };
}

- (NSArray<NSDictionary *> *)deviceList {
  NSMutableArray<NSDictionary *> *devices = [NSMutableArray array];
  for (NSString *identifier in [[self.devices allKeys] sortedArrayUsingSelector:@selector(compare:)]) {
    NSMutableDictionary *device = [self.devices[identifier] mutableCopy];
    device[@"connected"] = @([self.connectionState isEqualToString:@"connected"] && [self.connectedPeripheral.identifier.UUIDString isEqualToString:identifier]);
    [devices addObject:device];
  }
  return devices;
}

- (NSString *)bluetoothState {
  switch (self.central.state) {
    case CBManagerStatePoweredOn: return @"poweredOn";
    case CBManagerStatePoweredOff: return @"poweredOff";
    case CBManagerStateUnauthorized: return @"unauthorized";
    default: return @"unknown";
  }
}

- (NSString *)microphoneState {
  return [[AVAudioSession sharedInstance] recordPermission] == AVAudioSessionRecordPermissionGranted ? @"granted" : @"denied";
}

@end
