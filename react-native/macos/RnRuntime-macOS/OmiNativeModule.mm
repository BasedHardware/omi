#import "OmiNativeModule.h"
#import "OmiBackendModule.h"
#import <React/RCTBridge.h>
#import "../../apple/OmiDeviceInformation.h"
#import "../../apple/OmiBleSession.h"
#import "../../apple/OmiDeviceControls.h"
#import <math.h>

#import <CoreBluetooth/CoreBluetooth.h>
#import <TargetConditionals.h>
#if !TARGET_OS_OSX
#import <AVFAudio/AVFAudio.h>
#import <UserNotifications/UserNotifications.h>
#endif

static NSString *const OmiButtonServiceUUID = @"23ba7924-0000-1000-7450-346eac492e92";
static NSString *const OmiButtonUUID = @"23ba7925-0000-1000-7450-346eac492e92";
static NSString *const OmiStorageServiceUUID = @"30295780-4301-eabd-2904-2849adfeae43";
static NSString *const OmiStorageStatusUUID = @"30295782-4301-eabd-2904-2849adfeae43";
static NSString *const OmiHapticServiceUUID = @"cab1ab95-2ea5-4f4d-bb56-874b72cfc984";
static NSString *const OmiHapticUUID = @"cab1ab96-2ea5-4f4d-bb56-874b72cfc984";
static NSString *const OmiServiceUUID = @"19b10000-e8f2-537e-4f6c-d104768a1214";
static NSString *const OmiAudioUUID = @"19b10001-e8f2-537e-4f6c-d104768a1214";
static NSString *const OmiCodecUUID = @"19b10002-e8f2-537e-4f6c-d104768a1214";
static NSString *const OmiBatteryServiceUUID = @"180F";
static NSString *const OmiBatteryLevelUUID = @"2A19";
static NSString *const OmiInformationServiceUUID = @"180A";
static NSString *const OmiFeaturesServiceUUID = @"19b10020-e8f2-537e-4f6c-d104768a1214";
static NSString *const OmiFeaturesUUID = @"19b10021-e8f2-537e-4f6c-d104768a1214";
static NSString *const OmiSettingsServiceUUID = @"19b10010-e8f2-537e-4f6c-d104768a1214";
static NSString *const OmiLedUUID = @"19b10011-e8f2-537e-4f6c-d104768a1214";
static NSString *const OmiGainUUID = @"19b10012-e8f2-537e-4f6c-d104768a1214";
static NSString *const OmiChargingUUID = @"19b10013-e8f2-537e-4f6c-d104768a1214";

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
@property(nonatomic) OmiBleReconnectState reconnectState;
@property(nonatomic) OmiBleFirstAudio firstAudio;
@property(nonatomic, strong) CBPeripheral *reconnectPeripheral;
@property(nonatomic) BOOL buttonNotifying;
@property(nonatomic) BOOL buttonSubscriptionRequested;
@property(nonatomic) BOOL audioNotifying;
@property(nonatomic, strong) NSNumber *codec;
@property(nonatomic, copy) RCTPromiseResolveBlock scanResolve;
@property(nonatomic, copy) RCTPromiseResolveBlock connectResolve;
@property(nonatomic, copy) RCTPromiseRejectBlock connectReject;
@property(nonatomic) NSInteger scanGeneration;
@property(nonatomic) NSUInteger connectionGeneration;
@property(nonatomic, strong) NSMutableDictionary<NSString *, CBCharacteristic *> *settingCharacteristics;
@property(nonatomic, strong) CBCharacteristic *pendingSettingCharacteristic;
@property(nonatomic, copy) NSString *pendingSetting;
@property(nonatomic, strong) NSNumber *pendingSettingValue;
@property(nonatomic, copy) RCTPromiseResolveBlock settingResolve;
@property(nonatomic, copy) RCTPromiseRejectBlock settingReject;
@property(nonatomic) BOOL settingWritten;
@property(nonatomic) NSUInteger settingGeneration;
@property(nonatomic) OmiFindPattern findPattern;
@property(nonatomic) NSUInteger findTicket;
@property(nonatomic, copy) RCTPromiseResolveBlock storageResolve;
@property(nonatomic, copy) RCTPromiseRejectBlock storageReject;
@property(nonatomic, strong) NSMutableSet<CBPeripheral *> *retiringPeripherals;
@property(nonatomic) BOOL awaitingAdapterForScan;
@property(nonatomic, strong) NSNumber *pendingScanTimeoutSeconds;
@property(nonatomic, copy) NSArray<NSString *> *pendingScanServiceUuids;
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

- (void)invalidate {
  [self cancelReconnect];
  [self retireConnection:@"Omi Bluetooth session closed"];
  self.central.delegate = nil;
  [super invalidate];
}

- (void)stopObserving {
  self.observing = NO;
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _settingCharacteristics = [NSMutableDictionary dictionary];
    _retiringPeripherals = [NSMutableSet set];
    _peripherals = [NSMutableDictionary dictionary];
    _devices = [NSMutableDictionary dictionary];
    _batteries = [NSMutableDictionary dictionary];
    _connectionState = @"disconnected";
    _lastEvent = @"Bluetooth adapter not checked";
  }
  return self;
}

- (void)ensureCentral {
  if (self.central != nil) {
    return;
  }
  self.central = [[CBCentralManager alloc] initWithDelegate:self queue:dispatch_get_main_queue()];
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
  self.awaitingAdapterForScan = NO;
  [self ensureCentral];
  if (self.central.state != CBManagerStatePoweredOn) {
    if (self.central.state == CBManagerStateUnknown || self.central.state == CBManagerStateResetting) {
      self.awaitingAdapterForScan = YES;
      self.pendingScanTimeoutSeconds = timeoutSeconds;
      self.pendingScanServiceUuids = serviceUuids;
      self.scanResolve = resolve;
      return;
    }
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
  CBPeripheral *retained = self.connectedPeripheral ?: self.reconnectPeripheral;
  if (![self.connectionState isEqualToString:@"disconnected"] && retained != nil) {
    keepId = retained.identifier.UUIDString;
    kept = self.devices[keepId];
    if (kept == nil) {
      kept = [self deviceDictionary:keepId name:retained.name rssi:nil];
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
  self.awaitingAdapterForScan = NO;
  self.pendingScanTimeoutSeconds = nil;
  self.pendingScanServiceUuids = nil;
  if (self.central != nil) {
    [self.central stopScan];
  }
  self.scanning = NO;
  self.lastEvent = @"Omi scan stopped";
  if (self.scanResolve != nil) {
    self.scanResolve([self deviceList]);
    self.scanResolve = nil;
  }
  resolve(nil);
}

- (void)rememberedAction:(NSString *)action resolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject {
  NSString *identifier = self.connectedPeripheral.identifier.UUIDString;
  NSUInteger generation = self.connectionGeneration;
  BOOL ready = OmiBleRecordingReady([self.connectionState isEqual:@"connected"], self.audioNotifying, self.codec != nil);
  if ([action isEqual:@"save"] && !ready) { reject(@"OMI_REMEMBERED_DEVICE", @"Connect your Omi before remembering it", nil); return; }
  NSDictionary *device = identifier == nil ? nil : @{@"id":identifier, @"name":self.devices[identifier][@"name"] ?: @"Omi"};
  OmiBackendModule *backend = [self.bridge moduleForClass:OmiBackendModule.class];
  if (backend == nil) { reject(@"OMI_REMEMBERED_DEVICE", @"Remembered device storage is unavailable", nil); return; }
  [backend rememberedDevice:action device:device current:^BOOL {
    return ![action isEqual:@"save"] || (self.connectionGeneration == generation && [self.connectedPeripheral.identifier.UUIDString isEqual:identifier] && OmiBleRecordingReady([self.connectionState isEqual:@"connected"], self.audioNotifying, self.codec != nil));
  } resolver:resolve rejecter:reject];
}
RCT_REMAP_METHOD(getRememberedDevice, rememberedGet:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject) { [self rememberedAction:@"get" resolver:resolve rejecter:reject]; }
RCT_REMAP_METHOD(rememberConnectedDevice, rememberedSave:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject) { [self rememberedAction:@"save" resolver:resolve rejecter:reject]; }
RCT_REMAP_METHOD(forgetRememberedDevice, rememberedForget:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject) { [self rememberedAction:@"forget" resolver:resolve rejecter:reject]; }

RCT_REMAP_METHOD(connectDevice,
                 connectDeviceWithId:(NSString *)identifier
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  [self beginConnection:identifier recovering:NO resolver:resolve rejecter:reject];
}

- (void)beginConnection:(NSString *)identifier recovering:(BOOL)recovering resolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject {
  [self ensureCentral];
  CBPeripheral *peripheral = self.peripherals[identifier];
  if (peripheral == nil && self.central.state == CBManagerStatePoweredOn) {
    NSUUID *uuid = [[NSUUID alloc] initWithUUIDString:identifier];
    if (uuid != nil) peripheral = [self.central retrievePeripheralsWithIdentifiers:@[uuid]].firstObject;
    if (peripheral != nil) self.peripherals[identifier] = peripheral;
  }
  if (peripheral == nil || self.central.state != CBManagerStatePoweredOn || [self.retiringPeripherals containsObject:peripheral]) {
    reject(@"OMI_DEVICE_UNAVAILABLE", @"Omi device is unavailable", nil);
    return;
  }
  if (self.connectedPeripheral == peripheral) {
    reject(@"OMI_DEVICE_BUSY", @"Omi connection is already active", nil);
    return;
  }
  if (!recovering) [self cancelReconnect];
  if (self.connectResolve != nil) {
    self.connectReject(@"OMI_DEVICE_UNAVAILABLE", @"Omi connection was replaced", nil);
    self.connectResolve = nil;
    self.connectReject = nil;
  }
  [self.central stopScan];
  self.scanning = NO;
  [self finishSetting:nil error:@"Omi connection was replaced"];
  [self finishStorage:nil];
  [self.settingCharacteristics removeAllObjects];
  _firstAudio.cancel();
  self.buttonNotifying = NO;
  self.buttonSubscriptionRequested = NO;
  self.audioNotifying = NO;
  self.codec = nil;
  self.connectionState = @"connecting";
  CBPeripheral *existing = self.connectedPeripheral;
  if (existing != nil && existing != peripheral) {
    existing.delegate = nil;
    [self.retiringPeripherals addObject:existing];
    [self.central cancelPeripheralConnection:existing];
  }
  self.connectedPeripheral = peripheral;
  peripheral.delegate = self;
  self.connectResolve = resolve;
  self.connectReject = reject;
  NSUInteger generation = ++self.connectionGeneration;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 20 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
    if (OmiBleSetupExpired(self.connectionGeneration, generation, self.connectResolve != nil)) {
      [self retireConnection:@"Omi connection setup timed out"];
    }
  });
  [self emitSnapshot];
  [self.central connectPeripheral:peripheral options:nil];
}

RCT_REMAP_METHOD(disconnectDevice,
                 disconnectDeviceWithId:(NSString *)identifier
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  if ([self.connectedPeripheral.identifier.UUIDString isEqualToString:identifier] || [self.reconnectPeripheral.identifier.UUIDString isEqualToString:identifier]) {
    [self cancelReconnect];
    [self retireConnection:@"Disconnected from Omi"];
  }
  resolve(nil);
}

- (void)centralManagerDidUpdateState:(CBCentralManager *)central {
  if (central.state != CBManagerStatePoweredOn) {
    [self cancelReconnect];
    [self retireConnection:@"Bluetooth is unavailable"];
    self.scanning = NO;
    self.scanGeneration += 1;
    if (self.scanResolve != nil) { self.scanResolve([self deviceList]); self.scanResolve = nil; }
  }
  self.lastEvent = [self bluetoothLastEvent];
  [self emitSnapshot];
  if (!self.awaitingAdapterForScan || self.scanResolve == nil) {
    return;
  }
  self.awaitingAdapterForScan = NO;
  RCTPromiseResolveBlock pending = self.scanResolve;
  NSNumber *timeoutSeconds = self.pendingScanTimeoutSeconds;
  NSArray<NSString *> *serviceUuids = self.pendingScanServiceUuids;
  self.scanResolve = nil;
  self.pendingScanTimeoutSeconds = nil;
  self.pendingScanServiceUuids = nil;
  if (central.state == CBManagerStatePoweredOn) {
    [self startScanWithTimeout:timeoutSeconds serviceUuids:serviceUuids resolver:pending rejecter:nil];
    return;
  }
  self.lastEvent = @"Bluetooth is not powered on";
  pending(@[]);
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
  if (!OmiBleCallbackIsCurrent(self.connectedPeripheral, peripheral)) {
    [central cancelPeripheralConnection:peripheral];
    return;
  }
  for (NSString *field in @[ @"information", @"features", @"ledBrightness", @"microphoneGain", @"charging" ]) {
    [self.devices[peripheral.identifier.UUIDString] removeObjectForKey:field];
  }
  self.connectionState = @"connected";
  self.lastEvent = @"Connected to Omi";
  peripheral.delegate = self;
  [peripheral discoverServices:@[ [CBUUID UUIDWithString:OmiServiceUUID], [CBUUID UUIDWithString:OmiBatteryServiceUUID], [CBUUID UUIDWithString:OmiInformationServiceUUID], [CBUUID UUIDWithString:OmiFeaturesServiceUUID], [CBUUID UUIDWithString:OmiSettingsServiceUUID], [CBUUID UUIDWithString:OmiHapticServiceUUID], [CBUUID UUIDWithString:OmiStorageServiceUUID], [CBUUID UUIDWithString:OmiButtonServiceUUID] ]];
  [self emitSnapshot];
}

- (void)centralManager:(CBCentralManager *)central
didFailToConnectPeripheral:(CBPeripheral *)peripheral
                 error:(NSError *)error {
  [self.retiringPeripherals removeObject:peripheral];
  if (!OmiBleCallbackIsCurrent(self.connectedPeripheral, peripheral)) {
    return;
  }
  [self retireConnection:error.localizedDescription ?: @"Omi connection failed"];
  [self.retiringPeripherals removeObject:peripheral];
}

- (void)centralManager:(CBCentralManager *)central
didDisconnectPeripheral:(CBPeripheral *)peripheral
                 error:(NSError *)error {
  [self.retiringPeripherals removeObject:peripheral];
  if (!OmiBleCallbackIsCurrent(self.connectedPeripheral, peripheral)) {
    return;
  }
  [self retireConnection:error.localizedDescription ?: @"Disconnected from Omi"];
  [self.retiringPeripherals removeObject:peripheral];
}

- (void)peripheral:(CBPeripheral *)peripheral didDiscoverServices:(NSError *)error {
  if (!OmiBleCallbackIsCurrent(self.connectedPeripheral, peripheral)) return;
  if (error != nil) {
    [self retireConnection:@"Omi service discovery failed"];
    return;
  }
  for (CBService *service in peripheral.services) {
    if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiServiceUUID]]) {
      [peripheral discoverCharacteristics:@[ [CBUUID UUIDWithString:OmiAudioUUID], [CBUUID UUIDWithString:OmiCodecUUID] ]
                               forService:service];
    } else if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiStorageServiceUUID]]) {
      [peripheral discoverCharacteristics:@[ [CBUUID UUIDWithString:OmiStorageStatusUUID] ] forService:service];
    } else if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiHapticServiceUUID]]) {
      [peripheral discoverCharacteristics:@[ [CBUUID UUIDWithString:OmiHapticUUID] ] forService:service];
    } else if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiFeaturesServiceUUID]]) {
      [peripheral discoverCharacteristics:@[ [CBUUID UUIDWithString:OmiFeaturesUUID] ] forService:service];
    } else if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiButtonServiceUUID]]) {
      [peripheral discoverCharacteristics:@[ [CBUUID UUIDWithString:OmiButtonUUID] ] forService:service];
    } else if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiSettingsServiceUUID]]) {
      [peripheral discoverCharacteristics:@[ [CBUUID UUIDWithString:OmiLedUUID], [CBUUID UUIDWithString:OmiGainUUID], [CBUUID UUIDWithString:OmiChargingUUID] ] forService:service];
    } else if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiInformationServiceUUID]]) {
      NSMutableArray<CBUUID *> *uuids = [NSMutableArray array];
      for (NSString *uuid in OmiInformationFields()) [uuids addObject:[CBUUID UUIDWithString:uuid]];
      [peripheral discoverCharacteristics:uuids forService:service];
    } else if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiBatteryServiceUUID]]) {
      [peripheral discoverCharacteristics:@[ [CBUUID UUIDWithString:OmiBatteryLevelUUID] ] forService:service];
    }
  }
}

- (void)peripheral:(CBPeripheral *)peripheral didDiscoverCharacteristicsForService:(CBService *)service error:(NSError *)error {
  if (!OmiBleCallbackIsCurrent(self.connectedPeripheral, peripheral)) return;
  if (error != nil) {
    return;
  }
  for (CBCharacteristic *characteristic in service.characteristics) {
    if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiButtonServiceUUID]] && [characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiButtonUUID]]) {
      self.settingCharacteristics[OmiButtonUUID] = characteristic;
      [self subscribeButton];
    }
    if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiStorageServiceUUID]] && [characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiStorageStatusUUID]]) {
      self.settingCharacteristics[OmiStorageStatusUUID] = characteristic;
      [self emitSnapshot];
    }
    if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiHapticServiceUUID]] && [characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiHapticUUID]]) {
      self.settingCharacteristics[OmiHapticUUID] = characteristic;
      [self emitSnapshot];
    }
    if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiSettingsServiceUUID]]) self.settingCharacteristics[characteristic.UUID.UUIDString.lowercaseString] = characteristic;
    if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiFeaturesUUID]] && (characteristic.properties & CBCharacteristicPropertyRead) != 0) [peripheral readValueForCharacteristic:characteristic];
    if (OmiInformationFields()[characteristic.UUID.UUIDString] != nil &&
        (characteristic.properties & CBCharacteristicPropertyRead) != 0) {
      [peripheral readValueForCharacteristic:characteristic];
    }
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
  if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiSettingsServiceUUID]]) [self readSupportedSettings];
}

- (void)peripheral:(CBPeripheral *)peripheral
didUpdateNotificationStateForCharacteristic:(CBCharacteristic *)characteristic
             error:(NSError *)error {
  if (!OmiBleCallbackIsCurrent(self.connectedPeripheral, peripheral)) return;
  if (characteristic == self.settingCharacteristics[OmiButtonUUID]) {
    self.buttonNotifying = error == nil && characteristic.isNotifying;
    [self emitSnapshot];
    return;
  }
  if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiAudioUUID]]) {
    self.audioNotifying = error == nil && characteristic.isNotifying;
    if (!self.audioNotifying) { [self retireConnection:@"Omi audio notification subscription failed"]; return; }
    [self finishConnectionIfReady];
    [self emitSnapshot];
  }
}

- (void)peripheral:(CBPeripheral *)peripheral didUpdateValueForCharacteristic:(CBCharacteristic *)characteristic error:(NSError *)error {
  double capturedAtMs = floor(NSDate.date.timeIntervalSince1970 * 1000.0);
  if (!OmiBleCallbackIsCurrent(self.connectedPeripheral, peripheral)) return;
  if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiStorageStatusUUID]] && self.storageResolve != nil) {
    NSDictionary *status = error == nil ? OmiStorageStatus(characteristic.value) : nil;
    [self finishStorage:status];
    return;
  }
  if (error != nil || characteristic.value == nil) {
    if (self.settingWritten && self.pendingSettingCharacteristic == characteristic) [self finishSetting:nil error:@"Device setting read-back failed"];
    return;
  }
  if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiAudioUUID]] && _firstAudio.receive(characteristic.value.length)) [self emitSnapshot];
  NSString *identifier = peripheral.identifier.UUIDString;
  if (self.devices[identifier] == nil) self.devices[identifier] = [self deviceDictionary:identifier name:peripheral.name ?: @"Omi" rssi:nil];
  if (characteristic == self.settingCharacteristics[OmiButtonUUID]) {
    if (self.buttonNotifying && self.audioNotifying && OmiButtonSupported(self.devices[identifier][@"features"]) && OmiButtonDoublePress(characteristic.value))
      [self emit:@"button" body:@{ @"deviceId":identifier, @"connectionId":[NSString stringWithFormat:@"%lu", (unsigned long)self.connectionGeneration], @"action":@"doublePress" }];
    return;
  }
  if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiFeaturesUUID]]) {
    NSNumber *features = OmiDeviceFeatures(characteristic.value);
    if (features != nil) { self.devices[identifier][@"features"] = features; [self readSupportedSettings]; [self subscribeButton]; [self emitSnapshot]; }
    return;
  }
  NSString *setting = [characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiLedUUID]] ? @"ledBrightness" : [characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiGainUUID]] ? @"microphoneGain" : nil;
  if (setting != nil) {
    if (!OmiDeviceSettingSupported(self.devices[identifier][@"features"], setting)) return;
    NSNumber *value = OmiDeviceSettingValue(setting, characteristic.value);
    if (value != nil) self.devices[identifier][setting] = value;
    else [self.devices[identifier] removeObjectForKey:setting];
    if (self.settingWritten && self.pendingSettingCharacteristic == characteristic) {
      BOOL confirmed = value != nil && [value isEqualToNumber:self.pendingSettingValue];
      [self finishSetting:confirmed ? value : nil error:confirmed ? nil : @"Device did not confirm the requested setting"];
    }
    [self emitSnapshot];
    return;
  }
  if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiChargingUUID]]) {
    if (self.devices[identifier][@"features"] != nil && characteristic.value.length == 1) {
      uint8_t value = ((const uint8_t *)characteristic.value.bytes)[0];
      if (value <= 1) { self.devices[identifier][@"charging"] = @(value == 1); [self emitSnapshot]; }
    }
    return;
  }
  NSString *field = OmiInformationFields()[characteristic.UUID.UUIDString];
  if (field != nil) {
    NSString *value = OmiDecodeDeviceInformation(characteristic.value);
    if (value != nil) {
      NSMutableDictionary *device = self.devices[identifier];
      NSMutableDictionary *information = [device[@"information"] mutableCopy] ?: [NSMutableDictionary dictionary];
      information[field] = value;
      device[@"information"] = information;
      [self emitSnapshot];
    }
    return;
  }
  if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiCodecUUID]] && characteristic.value.length > 0) {
    const unsigned char *bytes = (const unsigned char *)characteristic.value.bytes;
    self.codec = @(bytes[0]);
    [self finishConnectionIfReady];
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
  if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiAudioUUID]] && characteristic.value.length > 0 && OmiBleRecordingReady([self.connectionState isEqualToString:@"connected"], self.audioNotifying, self.codec != nil)) {
    NSMutableDictionary *audio = [@{
            @"deviceId": identifier,
            @"codec": self.codec,
            @"connectionId": [NSString stringWithFormat:@"%lu", (unsigned long)self.connectionGeneration],
            @"payloadBase64": [characteristic.value base64EncodedStringWithOptions:0],
          } mutableCopy];
    if (isfinite(capturedAtMs) && capturedAtMs >= 0 && capturedAtMs <= 8640000000000000.0) audio[@"capturedAtMs"] = @(capturedAtMs);
    [self emit:@"audio" body:audio];
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
  NSString *connectedId = (self.connectedPeripheral ?: self.reconnectPeripheral).identifier.UUIDString;
  NSMutableDictionary *snapshot = [@{
    @"bluetooth": [self bluetoothState],
    @"devices": [self deviceList],
    @"connectedDeviceId": connectedId ?: [NSNull null],
    @"phase": self.connectionState,
    @"capture": OmiBleRecordingReady([self.connectionState isEqualToString:@"connected"], self.audioNotifying, self.codec != nil) ? @"recording" : @"idle",
    @"lastEvent": self.lastEvent,
    @"microphone": @"unknown",
    @"notifications": @"unknown",
  } mutableCopy];
  if ([self.connectionState isEqual:@"connected"]) snapshot[@"audioStatus"] = _firstAudio.observed ? @"active" : @"waiting";
  if (self.codec != nil) {
    snapshot[@"codec"] = self.codec;
  }
#if !TARGET_OS_OSX
  snapshot[@"captureMode"] = @"stream";
  snapshot[@"microphone"] = [self microphoneState];
  snapshot[@"background"] = @"inactive";
  snapshot[@"audioRoute"] = @"phone-mic";
#endif
  if (self.connectedPeripheral != nil) snapshot[@"connectionId"] = [NSString stringWithFormat:@"%lu", (unsigned long)self.connectionGeneration];
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
    device[@"buttonSupported"] = @([device[@"connected"] boolValue] && self.buttonNotifying && OmiButtonSupported(device[@"features"]));
    CBCharacteristic *storage = self.settingCharacteristics[OmiStorageStatusUUID];
    device[@"storageStatusSupported"] = @([device[@"connected"] boolValue] && OmiStorageSupported(device[@"features"]) && storage != nil && (storage.properties & CBCharacteristicPropertyRead) != 0);
    CBCharacteristic *haptic = self.settingCharacteristics[OmiHapticUUID];
    device[@"findDeviceSupported"] = @([device[@"connected"] boolValue] && haptic != nil && (haptic.properties & CBCharacteristicPropertyWrite) != 0);
    [devices addObject:[device copy]];
  }
  return devices;
}

- (NSMutableDictionary *)deviceDictionary:(NSString *)identifier name:(id)name rssi:(NSNumber *)rssi {
  NSMutableDictionary *device = [@{
    @"id": identifier,
    @"name": [name isKindOfClass:[NSString class]] ? name : @"Omi",
    @"connected": @([self.connectionState isEqualToString:@"connected"] &&
                    [self.connectedPeripheral.identifier.UUIDString isEqualToString:identifier]),
  } mutableCopy];
  if (rssi != nil) device[@"rssi"] = rssi;
  for (NSString *field in @[ @"features", @"ledBrightness", @"microphoneGain", @"charging" ]) {
    if (self.devices[identifier][field] != nil) device[field] = self.devices[identifier][field];
  }
  NSDictionary *information = self.devices[identifier][@"information"];
  if (information != nil) device[@"information"] = information;
  NSNumber *battery = self.batteries[identifier];
  if (battery != nil) {
    device[@"battery"] = battery;
  }
  return device;
}

- (void)subscribeButton {
  CBCharacteristic *button = self.settingCharacteristics[OmiButtonUUID];
  if (!self.buttonSubscriptionRequested && self.connectedPeripheral != nil && OmiButtonSupported(self.devices[self.connectedPeripheral.identifier.UUIDString][@"features"]) && (button.properties & CBCharacteristicPropertyNotify) != 0) {
    self.buttonSubscriptionRequested = YES;
    [self.connectedPeripheral setNotifyValue:YES forCharacteristic:button];
  }
}

- (void)readSupportedSettings {
  CBPeripheral *peripheral = self.connectedPeripheral;
  if (peripheral == nil) return;
  NSNumber *features = self.devices[peripheral.identifier.UUIDString][@"features"];
  if (features == nil) return;
  NSDictionary *settings = @{ @"ledBrightness": OmiLedUUID, @"microphoneGain": OmiGainUUID };
  for (NSString *setting in settings) {
    CBCharacteristic *characteristic = self.settingCharacteristics[settings[setting]];
    if (OmiDeviceSettingSupported(features, setting) && (characteristic.properties & CBCharacteristicPropertyRead) != 0) [peripheral readValueForCharacteristic:characteristic];
  }
  CBCharacteristic *charging = self.settingCharacteristics[OmiChargingUUID];
  if ((charging.properties & CBCharacteristicPropertyRead) != 0) [peripheral readValueForCharacteristic:charging];
  if ((charging.properties & CBCharacteristicPropertyNotify) != 0) [peripheral setNotifyValue:YES forCharacteristic:charging];
}

RCT_REMAP_METHOD(readStorageStatus,
                 readStorageStatusWithId:(NSString *)identifier
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  CBPeripheral *peripheral = self.connectedPeripheral;
  CBCharacteristic *characteristic = self.settingCharacteristics[OmiStorageStatusUUID];
  if (peripheral == nil || ![peripheral.identifier.UUIDString isEqualToString:identifier] ||
      ![self.connectionState isEqualToString:@"connected"] || self.settingResolve != nil || self.storageResolve != nil ||
      !OmiStorageSupported(self.devices[identifier][@"features"]) || characteristic == nil ||
      (characteristic.properties & CBCharacteristicPropertyRead) == 0) {
    reject(@"OMI_STORAGE_STATUS_FAILED", @"Storage status is unavailable", nil);
    return;
  }
  self.storageResolve = resolve;
  self.storageReject = reject;
  NSUInteger generation = ++self.settingGeneration;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 8 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
    if (self.storageResolve != nil && self.settingGeneration == generation) [self retireConnection:@"Storage status read timed out"];
  });
  [peripheral readValueForCharacteristic:characteristic];
}

- (void)finishStorage:(NSDictionary *)status {
  RCTPromiseResolveBlock resolve = self.storageResolve;
  RCTPromiseRejectBlock reject = self.storageReject;
  self.storageResolve = nil;
  self.storageReject = nil;
  self.settingGeneration += 1;
  if (status != nil && resolve != nil) resolve(status);
  else if (reject != nil) reject(@"OMI_STORAGE_STATUS_FAILED", @"Storage status is unavailable", nil);
}

RCT_REMAP_METHOD(findDevice,
                 findDeviceWithId:(NSString *)identifier
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  CBPeripheral *peripheral = self.connectedPeripheral;
  CBCharacteristic *characteristic = self.settingCharacteristics[OmiHapticUUID];
  if (peripheral == nil || ![peripheral.identifier.UUIDString isEqualToString:identifier] ||
      ![self.connectionState isEqualToString:@"connected"] || self.settingResolve != nil || self.storageResolve != nil ||
      characteristic == nil || (characteristic.properties & CBCharacteristicPropertyWrite) == 0) {
    reject(@"OMI_FIND_DEVICE_FAILED", @"Find device is unavailable", nil);
    return;
  }
  self.pendingSetting = @"findDevice";
  self.pendingSettingCharacteristic = characteristic;
  self.settingResolve = ^(id value) { resolve(nil); };
  self.settingReject = reject;
  self.findTicket = _findPattern.begin();
  [self sendFindCommand:self.findTicket peripheral:peripheral];
}

- (void)sendFindCommand:(NSUInteger)ticket peripheral:(CBPeripheral *)peripheral {
  if (!OmiBleCallbackIsCurrent(self.connectedPeripheral, peripheral) || !_findPattern.send(ticket)) return;
  NSUInteger generation = ++self.settingGeneration;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 8 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
    if (self.settingResolve != nil && self.settingGeneration == generation) [self retireConnection:@"Find device command timed out"];
  });
  uint8_t byte = OmiFindPattern::level;
  [peripheral writeValue:[NSData dataWithBytes:&byte length:1] forCharacteristic:self.pendingSettingCharacteristic type:CBCharacteristicWriteWithResponse];
}

RCT_REMAP_METHOD(setDeviceSetting,
                 setDeviceSettingWithId:(NSString *)identifier
                 setting:(NSString *)setting
                 value:(double)value
                 resolver:(RCTPromiseResolveBlock)resolve
                 rejecter:(RCTPromiseRejectBlock)reject) {
  CBPeripheral *peripheral = self.connectedPeripheral;
  NSDictionary *device = self.devices[identifier];
  NSString *uuid = [setting isEqualToString:@"ledBrightness"] ? OmiLedUUID : [setting isEqualToString:@"microphoneGain"] ? OmiGainUUID : nil;
  CBCharacteristic *characteristic = uuid == nil ? nil : self.settingCharacteristics[uuid];
  if (peripheral == nil || ![peripheral.identifier.UUIDString isEqualToString:identifier] ||
      ![self.connectionState isEqualToString:@"connected"] || self.settingResolve != nil || self.storageResolve != nil ||
      !OmiDeviceSettingSupported(device[@"features"], setting) || device[setting] == nil ||
      !isfinite(value) || value != floor(value) || value < 0 || value > OmiDeviceSettingMaximum(setting) ||
      characteristic == nil || (characteristic.properties & CBCharacteristicPropertyRead) == 0 ||
      (characteristic.properties & CBCharacteristicPropertyWrite) == 0) {
    reject(@"OMI_DEVICE_SETTING_FAILED", @"Device setting is unavailable", nil);
    return;
  }
  self.pendingSetting = setting;
  self.pendingSettingValue = @(value);
  self.pendingSettingCharacteristic = characteristic;
  self.settingWritten = NO;
  self.settingResolve = resolve;
  self.settingReject = reject;
  NSUInteger generation = ++self.settingGeneration;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 8 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
    if (self.settingResolve != nil && self.settingGeneration == generation) [self retireConnection:@"Device setting confirmation timed out"];
  });
  uint8_t byte = (uint8_t)value;
  [peripheral writeValue:[NSData dataWithBytes:&byte length:1] forCharacteristic:characteristic type:CBCharacteristicWriteWithResponse];
}

- (void)peripheral:(CBPeripheral *)peripheral didWriteValueForCharacteristic:(CBCharacteristic *)characteristic error:(NSError *)error {
  if (!OmiBleCallbackIsCurrent(self.connectedPeripheral, peripheral) || self.pendingSettingCharacteristic != characteristic || self.settingResolve == nil) return;
  if (error != nil) { [self finishSetting:nil error:@"Device setting write failed"]; return; }
  if ([self.pendingSetting isEqualToString:@"findDevice"]) {
    if (!_findPattern.acknowledge(self.findTicket)) return;
    self.settingGeneration += 1;
    if (_findPattern.complete()) [self finishSetting:@3 error:nil];
    else {
      NSUInteger ticket = self.findTicket;
      dispatch_after(dispatch_time(DISPATCH_TIME_NOW, OmiFindPattern::delayMs * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        [self sendFindCommand:ticket peripheral:peripheral];
      });
    }
    return;
  }
  self.settingWritten = YES;
  [peripheral readValueForCharacteristic:characteristic];
}

- (void)finishSetting:(NSNumber *)value error:(NSString *)error {
  _findPattern.cancel();
  RCTPromiseResolveBlock resolve = self.settingResolve;
  RCTPromiseRejectBlock reject = self.settingReject;
  self.settingGeneration += 1;
  self.settingResolve = nil;
  self.settingReject = nil;
  self.pendingSetting = nil;
  self.pendingSettingValue = nil;
  self.pendingSettingCharacteristic = nil;
  self.settingWritten = NO;
  if (value != nil && resolve != nil) resolve(value);
  else if (reject != nil) reject(@"OMI_DEVICE_SETTING_FAILED", error ?: @"Device setting failed", nil);
}

- (void)watchFirstAudio:(CBPeripheral *)peripheral generation:(NSUInteger)generation {
  NSUInteger ticket = _firstAudio.generation;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, OmiBleFirstAudio::windowMs * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
    if (self.connectionGeneration != generation || !OmiBleCallbackIsCurrent(self.connectedPeripheral, peripheral)) return;
    int outcome = self->_firstAudio.timeout(ticket);
    if (outcome == 1) {
      CBCharacteristic *audio = nil;
      for (CBService *service in peripheral.services) if ([service.UUID isEqual:[CBUUID UUIDWithString:OmiServiceUUID]])
        for (CBCharacteristic *characteristic in service.characteristics) if ([characteristic.UUID isEqual:[CBUUID UUIDWithString:OmiAudioUUID]]) audio = characteristic;
      if (audio == nil) { [self retireConnection:@"Omi audio is unavailable"]; return; }
      [peripheral setNotifyValue:YES forCharacteristic:audio];
      [self watchFirstAudio:peripheral generation:generation];
    } else if (outcome == -1) { self.lastEvent = @"Omi connected · Waiting for audio"; [self emitSnapshot]; }
  });
}

- (void)finishConnectionIfReady {
  if (!self.audioNotifying || self.codec == nil || self.connectedPeripheral == nil) return;
  self.lastEvent = @"Omi audio notify is live";
  if (_firstAudio.begin()) [self watchFirstAudio:self.connectedPeripheral generation:self.connectionGeneration];
  self.reconnectPeripheral = self.connectedPeripheral;
  OmiBleReconnectReady(&_reconnectState);
  if (self.connectResolve != nil) {
    RCTPromiseResolveBlock resolve = self.connectResolve;
    self.connectResolve = nil;
    self.connectReject = nil;
    resolve(nil);
  }
}

- (void)retireConnection:(NSString *)message {
  self.connectionGeneration += 1;
  [self finishSetting:nil error:message];
  [self finishStorage:nil];
  [self.settingCharacteristics removeAllObjects];
  CBPeripheral *previous = self.connectedPeripheral;
  self.connectedPeripheral = nil;
  _firstAudio.cancel();
  self.buttonNotifying = NO;
  self.buttonSubscriptionRequested = NO;
  self.audioNotifying = NO;
  self.codec = nil;
  self.connectionState = @"disconnected";
  self.lastEvent = message;
  if (previous != nil) {
    previous.delegate = nil;
    [self.retiringPeripherals addObject:previous];
    if (previous.state != CBPeripheralStateDisconnected) {
      [self.central cancelPeripheralConnection:previous];
    }
  }
  if (self.connectReject != nil) {
    RCTPromiseRejectBlock reject = self.connectReject;
    self.connectResolve = nil;
    self.connectReject = nil;
    reject(@"OMI_DEVICE_UNAVAILABLE", message, nil);
  }
  [self emitSnapshot];
  CBPeripheral *target = self.reconnectPeripheral;
  NSInteger delay = OmiBleReconnectDelay(&_reconnectState);
  if (target != nil && delay >= 0) {
    self.connectionState = @"connecting";
    self.lastEvent = [NSString stringWithFormat:@"Reconnecting to Omi (%lu/3)", (unsigned long)self.reconnectState.attempts];
    NSUInteger generation = self.reconnectState.generation;
    [self emitSnapshot];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, delay * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
      if (!OmiBleReconnectAccepts(self.reconnectState, generation) || self.reconnectPeripheral != target) return;
      if (self.central.state != CBManagerStatePoweredOn) {
        [self cancelReconnect];
        [self retireConnection:@"Bluetooth is unavailable"];
      } else if ([self.retiringPeripherals containsObject:target]) {
        [self retireConnection:@"Waiting for the previous Omi connection to close"];
      } else {
        self.peripherals[target.identifier.UUIDString] = target;
        [self beginConnection:target.identifier.UUIDString recovering:YES resolver:^(id result) {} rejecter:^(NSString *code, NSString *message, NSError *error) {}];
      }
    });
  } else {
    self.reconnectPeripheral = nil;
    if (target != nil) {
      self.lastEvent = @"Omi reconnect failed. Connect your device to try again.";
      [self emitSnapshot];
    }
  }
}

- (void)cancelReconnect {
  OmiBleReconnectCancel(&_reconnectState);
  self.reconnectPeripheral = nil;
}

- (NSString *)bluetoothLastEvent {
  if (self.central == nil) {
    return @"Bluetooth adapter not checked";
  }
  switch (self.central.state) {
    case CBManagerStatePoweredOn: return @"Bluetooth is powered on";
    case CBManagerStatePoweredOff: return @"Bluetooth is not powered on";
    case CBManagerStateUnauthorized: return @"Bluetooth permission is required";
    default: return @"Bluetooth is unavailable";
  }
}

- (NSString *)bluetoothState {
  if (self.central == nil) {
    return @"unknown";
  }
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
