#import "OmiNativeModule.h"

#import <CoreBluetooth/CoreBluetooth.h>
#import <TargetConditionals.h>
#if !TARGET_OS_OSX
#import <AVFAudio/AVFAudio.h>
#import <UserNotifications/UserNotifications.h>
#endif

static NSString *const OmiServiceUUID = @"19b10000-e8f2-537e-4f6c-d104768a1214";
static NSString *const OmiAudioUUID = @"19b10001-e8f2-537e-4f6c-d104768a1214";
static NSString *const OmiCodecUUID = @"19b10002-e8f2-537e-4f6c-d104768a1214";
static NSString *const OmiBatteryServiceUUID = @"180F";
static NSString *const OmiBatteryLevelUUID = @"2A19";

@interface OmiNativeModule () <CBCentralManagerDelegate, CBPeripheralDelegate>
@property(nonatomic, strong) CBCentralManager *central;
@property(nonatomic, strong) NSMutableDictionary<NSString *, CBPeripheral *> *peripherals;
@property(nonatomic, strong) NSMutableDictionary<NSString *, NSMutableDictionary *> *devices;
@property(nonatomic, strong) NSMutableDictionary<NSString *, NSNumber *> *batteries;
@property(nonatomic, strong) CBPeripheral *connectedPeripheral;
@property(nonatomic, copy) NSString *connectionState;
@property(nonatomic, copy) NSString *lastEvent;
@property(nonatomic) BOOL scanning;
@property(nonatomic) BOOL observing;
@property(nonatomic) BOOL audioNotifying;
@property(nonatomic, strong) NSNumber *codec;
@property(nonatomic, copy) RCTPromiseResolveBlock scanResolve;
@property(nonatomic, copy) RCTPromiseResolveBlock connectResolve;
@property(nonatomic, copy) RCTPromiseRejectBlock connectReject;
@property(nonatomic) NSInteger scanGeneration;
@end

@implementation OmiNativeModule

RCT_EXPORT_MODULE(OmiNative)

+ (BOOL)requiresMainQueueSetup {
  return YES;
}

- (NSArray<NSString *> *)supportedEvents {
  return @[ @"omiNativeEvent" ];
}

- (void)startObserving {
  self.observing = YES;
}

- (void)stopObserving {
  self.observing = NO;
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _peripherals = [NSMutableDictionary dictionary];
    _devices = [NSMutableDictionary dictionary];
    _batteries = [NSMutableDictionary dictionary];
    _connectionState = @"disconnected";
    _lastEvent = @"Bluetooth adapter not checked";
    _central = [[CBCentralManager alloc] initWithDelegate:self queue:dispatch_get_main_queue()];
  }
  return self;
}

RCT_REMAP_METHOD(getSnapshot,
                 getSnapshotWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
#if TARGET_OS_OSX
  resolve([self snapshotDictionary]);
#else
  [[UNUserNotificationCenter currentNotificationCenter] getNotificationSettingsWithCompletionHandler:^(UNNotificationSettings *settings) {
    dispatch_async(dispatch_get_main_queue(), ^{
      resolve([self snapshotWithNotifications:settings.authorizationStatus]);
    });
  }];
#endif
}

RCT_REMAP_METHOD(getBluetoothState,
                 getBluetoothStateWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  resolve([self bluetoothState]);
}

RCT_REMAP_METHOD(requestPermissions,
                 requestPermissionsWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
#if TARGET_OS_OSX
  resolve(@{ @"microphone": @"unknown", @"notifications": @"unknown" });
#else
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
#endif
}

RCT_REMAP_METHOD(startScan,
                 startScanWithTimeout:(NSNumber *)timeoutSeconds
                 serviceUuids:(NSArray<NSString *> *)serviceUuids
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  if (self.scanResolve != nil) {
    self.scanResolve([self deviceList]);
    self.scanResolve = nil;
  }
  if (self.central.state != CBManagerStatePoweredOn) {
    self.lastEvent = @"Bluetooth is not powered on";
    resolve(@[]);
    return;
  }
  NSMutableArray<CBUUID *> *uuids = [NSMutableArray array];
  for (NSString *uuid in serviceUuids.count ? serviceUuids : @[ OmiServiceUUID ]) {
    [uuids addObject:[CBUUID UUIDWithString:uuid]];
  }
  NSString *keepId = nil;
  NSMutableDictionary *kept = nil;
  if (![self.connectionState isEqualToString:@"disconnected"] && self.connectedPeripheral != nil) {
    keepId = self.connectedPeripheral.identifier.UUIDString;
    kept = self.devices[keepId];
    if (kept == nil) {
      kept = [self deviceDictionary:keepId name:self.connectedPeripheral.name rssi:@0];
    }
  }
  [self.devices removeAllObjects];
  if (keepId.length > 0 && kept != nil) {
    self.devices[keepId] = kept;
  }
  [self.central scanForPeripheralsWithServices:uuids options:@{ CBCentralManagerScanOptionAllowDuplicatesKey: @NO }];
  self.scanning = YES;
  self.lastEvent = @"Scanning for Omi devices";
  self.scanResolve = resolve;
  NSTimeInterval timeout = timeoutSeconds != nil ? MAX(0, timeoutSeconds.doubleValue) : 8;
  NSInteger generation = ++self.scanGeneration;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(timeout * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
    if (generation != self.scanGeneration || self.scanResolve == nil) {
      return;
    }
    [self.central stopScan];
    self.scanning = NO;
    RCTPromiseResolveBlock pending = self.scanResolve;
    self.scanResolve = nil;
    pending([self deviceList]);
  });
}

RCT_REMAP_METHOD(stopScan,
                 stopScanWithResolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  [self.central stopScan];
  self.scanning = NO;
  self.lastEvent = @"Omi scan stopped";
  if (self.scanResolve != nil) {
    self.scanResolve([self deviceList]);
    self.scanResolve = nil;
  }
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
  if (self.connectResolve != nil) {
    self.connectReject(@"OMI_DEVICE_UNAVAILABLE", @"Omi connection was replaced", nil);
    self.connectResolve = nil;
    self.connectReject = nil;
  }
  [self.central stopScan];
  self.scanning = NO;
  self.audioNotifying = NO;
  self.codec = nil;
  self.connectionState = @"connecting";
  self.connectedPeripheral = peripheral;
  peripheral.delegate = self;
  self.connectResolve = resolve;
  self.connectReject = reject;
  [self emitSnapshot];
  [self.central connectPeripheral:peripheral options:nil];
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
  [self emitSnapshot];
}

- (void)centralManager:(CBCentralManager *)central
 didDiscoverPeripheral:(CBPeripheral *)peripheral
     advertisementData:(NSDictionary<NSString *, id> *)advertisementData
                  RSSI:(NSNumber *)RSSI {
  NSString *identifier = peripheral.identifier.UUIDString;
  self.peripherals[identifier] = peripheral;
  NSMutableDictionary *device = [self deviceDictionary:identifier
                                                  name:peripheral.name ?: advertisementData[CBAdvertisementDataLocalNameKey] ?: @"Omi"
                                                  rssi:RSSI];
  self.devices[identifier] = device;
  self.lastEvent = [NSString stringWithFormat:@"Found %lu Omi device%@", (unsigned long)self.devices.count, self.devices.count == 1 ? @"" : @"s"];
  [self emit:@"discovery" body:@{ @"device": [device copy] }];
}

- (void)centralManager:(CBCentralManager *)central didConnectPeripheral:(CBPeripheral *)peripheral {
  self.connectionState = @"connected";
  self.lastEvent = @"Connected to Omi";
  peripheral.delegate = self;
  [peripheral discoverServices:@[ [CBUUID UUIDWithString:OmiServiceUUID], [CBUUID UUIDWithString:OmiBatteryServiceUUID] ]];
  if (self.connectResolve != nil) {
    RCTPromiseResolveBlock resolve = self.connectResolve;
    self.connectResolve = nil;
    self.connectReject = nil;
    resolve(nil);
  }
  [self emitSnapshot];
}

- (void)centralManager:(CBCentralManager *)central
didFailToConnectPeripheral:(CBPeripheral *)peripheral
                 error:(NSError *)error {
  self.connectionState = @"disconnected";
  self.connectedPeripheral = nil;
  self.audioNotifying = NO;
  self.lastEvent = error.localizedDescription ?: @"Omi connection failed";
  if (self.connectReject != nil) {
    RCTPromiseRejectBlock reject = self.connectReject;
    self.connectResolve = nil;
    self.connectReject = nil;
    reject(@"OMI_DEVICE_UNAVAILABLE", self.lastEvent, error);
  }
  [self emitSnapshot];
}

- (void)centralManager:(CBCentralManager *)central
didDisconnectPeripheral:(CBPeripheral *)peripheral
                 error:(NSError *)error {
  self.connectionState = @"disconnected";
  self.connectedPeripheral = nil;
  self.audioNotifying = NO;
  self.codec = nil;
  self.lastEvent = error.localizedDescription ?: @"Disconnected from Omi";
  [self emitSnapshot];
}

- (void)peripheral:(CBPeripheral *)peripheral didDiscoverServices:(NSError *)error {
  if (error != nil) {
    self.lastEvent = error.localizedDescription;
    return;
  }
  for (CBService *service in peripheral.services) {
    if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiServiceUUID]]) {
      [peripheral discoverCharacteristics:@[ [CBUUID UUIDWithString:OmiAudioUUID], [CBUUID UUIDWithString:OmiCodecUUID] ]
                               forService:service];
    } else if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiBatteryServiceUUID]]) {
      [peripheral discoverCharacteristics:@[ [CBUUID UUIDWithString:OmiBatteryLevelUUID] ] forService:service];
    }
  }
}

- (void)peripheral:(CBPeripheral *)peripheral didDiscoverCharacteristicsForService:(CBService *)service error:(NSError *)error {
  if (error != nil) {
    return;
  }
  for (CBCharacteristic *characteristic in service.characteristics) {
    if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiAudioUUID]]) {
      [peripheral setNotifyValue:YES forCharacteristic:characteristic];
    } else if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiCodecUUID]] ||
               [characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiBatteryLevelUUID]]) {
      [peripheral readValueForCharacteristic:characteristic];
    }
    if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiBatteryLevelUUID]]) {
      [peripheral setNotifyValue:YES forCharacteristic:characteristic];
    }
  }
}

- (void)peripheral:(CBPeripheral *)peripheral
didUpdateNotificationStateForCharacteristic:(CBCharacteristic *)characteristic
             error:(NSError *)error {
  if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiAudioUUID]]) {
    self.audioNotifying = error == nil && characteristic.isNotifying;
    self.lastEvent = self.audioNotifying ? @"Omi audio notify is live" : @"Omi audio notify is idle";
    [self emitSnapshot];
  }
}

- (void)peripheral:(CBPeripheral *)peripheral didUpdateValueForCharacteristic:(CBCharacteristic *)characteristic error:(NSError *)error {
  if (error != nil || characteristic.value == nil) {
    return;
  }
  NSString *identifier = peripheral.identifier.UUIDString;
  if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiCodecUUID]] && characteristic.value.length > 0) {
    const unsigned char *bytes = (const unsigned char *)characteristic.value.bytes;
    self.codec = @(bytes[0]);
    [self emitSnapshot];
    return;
  }
  if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiBatteryLevelUUID]] && characteristic.value.length > 0) {
    const unsigned char *bytes = (const unsigned char *)characteristic.value.bytes;
    NSNumber *level = @(bytes[0]);
    self.batteries[identifier] = level;
    NSMutableDictionary *device = self.devices[identifier];
    if (device != nil) {
      device[@"battery"] = level;
    }
    [self emit:@"battery" body:@{ @"deviceId": identifier, @"battery": level }];
    [self emitSnapshot];
    return;
  }
  if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiAudioUUID]] && self.codec != nil) {
    [self emit:@"audio"
          body:@{
            @"deviceId": identifier,
            @"codec": self.codec,
            @"payloadBase64": [characteristic.value base64EncodedStringWithOptions:0],
          }];
  }
}

- (void)emitSnapshot {
  [self emit:@"snapshot" body:@{ @"snapshot": [self snapshotDictionary] }];
}

- (void)emit:(NSString *)type body:(NSDictionary *)body {
  if (!self.observing) {
    return;
  }
  NSMutableDictionary *payload = [body mutableCopy];
  payload[@"type"] = type;
  [self sendEventWithName:@"omiNativeEvent" body:payload];
}

- (NSDictionary *)snapshotDictionary {
  NSString *connectedId = [self.connectionState isEqualToString:@"connected"] ? self.connectedPeripheral.identifier.UUIDString : nil;
  NSMutableDictionary *snapshot = [@{
    @"bluetooth": [self bluetoothState],
    @"devices": [self deviceList],
    @"connectedDeviceId": connectedId ?: [NSNull null],
    @"phase": self.connectionState,
    @"capture": self.audioNotifying ? @"recording" : @"idle",
    @"lastEvent": self.lastEvent,
    @"microphone": @"unknown",
    @"notifications": @"unknown",
  } mutableCopy];
  if (self.codec != nil) {
    snapshot[@"codec"] = self.codec;
  }
#if !TARGET_OS_OSX
  snapshot[@"captureMode"] = @"stream";
  snapshot[@"microphone"] = [self microphoneState];
  snapshot[@"background"] = @"inactive";
  snapshot[@"audioRoute"] = @"phone-mic";
#endif
  return snapshot;
}

#if !TARGET_OS_OSX
- (NSDictionary *)snapshotWithNotifications:(UNAuthorizationStatus)notificationStatus {
  NSMutableDictionary *snapshot = [[self snapshotDictionary] mutableCopy];
  snapshot[@"notifications"] = notificationStatus == UNAuthorizationStatusAuthorized ? @"granted" : @"denied";
  return snapshot;
}
#endif

- (NSArray<NSDictionary *> *)deviceList {
  NSMutableArray<NSDictionary *> *devices = [NSMutableArray array];
  for (NSString *identifier in [[self.devices allKeys] sortedArrayUsingSelector:@selector(compare:)]) {
    NSMutableDictionary *device = self.devices[identifier];
    device[@"connected"] = @([self.connectionState isEqualToString:@"connected"] &&
                             [self.connectedPeripheral.identifier.UUIDString isEqualToString:identifier]);
    NSNumber *battery = self.batteries[identifier];
    if (battery != nil) {
      device[@"battery"] = battery;
    }
    [devices addObject:[device copy]];
  }
  return devices;
}

- (NSMutableDictionary *)deviceDictionary:(NSString *)identifier name:(id)name rssi:(NSNumber *)rssi {
  NSMutableDictionary *device = [@{
    @"id": identifier,
    @"name": [name isKindOfClass:[NSString class]] ? name : @"Omi",
    @"rssi": rssi ?: @0,
    @"connected": @([self.connectionState isEqualToString:@"connected"] &&
                    [self.connectedPeripheral.identifier.UUIDString isEqualToString:identifier]),
  } mutableCopy];
  NSNumber *battery = self.batteries[identifier];
  if (battery != nil) {
    device[@"battery"] = battery;
  }
  return device;
}

- (NSString *)bluetoothState {
  switch (self.central.state) {
    case CBManagerStatePoweredOn: return @"poweredOn";
    case CBManagerStatePoweredOff: return @"poweredOff";
    case CBManagerStateUnauthorized: return @"unauthorized";
    default: return @"unknown";
  }
}

#if !TARGET_OS_OSX
- (NSString *)microphoneState {
  return [[AVAudioSession sharedInstance] recordPermission] == AVAudioSessionRecordPermissionGranted ? @"granted" : @"denied";
}
#endif

@end
