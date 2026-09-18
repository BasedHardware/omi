#import <Foundation/Foundation.h>
#import <CoreBluetooth/CoreBluetooth.h>
#import <dispatch/dispatch.h>
#include <cassert>

static NSMutableArray *timers;
static void recordTimer(dispatch_time_t time, dispatch_queue_t queue, dispatch_block_t block) {
  [timers addObject:[block copy]];
}
#define dispatch_after recordTimer
#if OMI_TEST_IOS_SOURCE
#import "../../ios/RnRuntime/OmiNativeModule.mm"
#else
#import "../../macos/RnRuntime-macOS/OmiNativeModule.mm"
#endif
#undef dispatch_after

@implementation RCTEventEmitter
- (void)invalidate {}
- (void)sendEventWithName:(NSString *)name body:(id)body {}
@end
@implementation RCTBridge
- (id)moduleForClass:(Class)module { return nil; }
@end
static NSString *restorableDevice;
static NSUInteger nativeAppends;
static BOOL nativeStorageFails;
@implementation OmiBackendModule
- (void)rememberedDevice:(NSString *)action device:(NSDictionary *)device current:(BOOL (^)(void))current resolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject { abort(); }
- (void)prepareBleRecording:(NSDictionary *)device restoring:(BOOL)restoring current:(BOOL (^)(void))current resolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject { assert(current()); resolve(nil); }
- (NSDictionary *)stopBleRecording:(BOOL)forget { if (forget) restorableDevice = nil; return nil; }
- (BOOL)appendBlePacket:(NSData *)packet codec:(NSNumber *)codec at:(NSNumber *)at sealed:(NSDictionary **)sealed { nativeAppends++; return !nativeStorageFails; }
- (void)rotateBleRecording {}
- (NSString *)restorableBleDeviceId { return restorableDevice; }
@end

@interface TestPeripheral : NSObject
@property(nonatomic, strong) NSUUID *identifier;
@property(nonatomic, weak) id delegate;
@property(nonatomic) CBPeripheralState state;
@property(nonatomic) NSUInteger reads;
@property(nonatomic) NSUInteger discoveries;
@property(nonatomic, copy) NSString *name;
- (void)readValueForCharacteristic:(CBCharacteristic *)characteristic;
- (void)discoverServices:(NSArray *)services;
@end
@implementation TestPeripheral
- (void)readValueForCharacteristic:(CBCharacteristic *)characteristic { self.reads++; }
- (void)discoverServices:(NSArray *)services { self.discoveries++; }
@end
@interface TestCentral : NSObject
@property(nonatomic, weak) id delegate;
@property(nonatomic) CBManagerState state;
@property(nonatomic) NSUInteger connects;
@property(nonatomic) NSUInteger cancellations;
- (void)stopScan;
- (void)cancelPeripheralConnection:(CBPeripheral *)peripheral;
- (void)connectPeripheral:(CBPeripheral *)peripheral options:(NSDictionary *)options;
@end
@implementation TestCentral
- (void)stopScan {}
- (void)cancelPeripheralConnection:(CBPeripheral *)peripheral { self.cancellations++; }
- (void)connectPeripheral:(CBPeripheral *)peripheral options:(NSDictionary *)options { self.connects++; }
@end

int main() {
  @autoreleasepool {
    timers = [NSMutableArray array];
    OmiNativeModule *module = [OmiNativeModule new];
    assert([module methodQueue] == dispatch_get_main_queue());
#if OMI_TEST_IOS_SOURCE
    module.captureBackend = [OmiBackendModule new];
#endif
    TestCentral *central = [TestCentral new]; central.state = CBManagerStatePoweredOn;
    module.central = (CBCentralManager *)central;
    TestPeripheral *a = [TestPeripheral new]; a.identifier = NSUUID.UUID; a.state = CBPeripheralStateConnected;
    TestPeripheral *b = [TestPeripheral new]; b.identifier = NSUUID.UUID; b.state = CBPeripheralStateDisconnected;
    module.peripherals[a.identifier.UUIDString] = (CBPeripheral *)a;
    module.peripherals[b.identifier.UUIDString] = (CBPeripheral *)b;
    module.connectedPeripheral = (CBPeripheral *)a;
    module.connectionState = @"connected";
    module.devices[a.identifier.UUIDString] = [@{@"features":@64} mutableCopy];
    CBMutableCharacteristic *storage = [[CBMutableCharacteristic alloc] initWithType:[CBUUID UUIDWithString:OmiStorageStatusUUID] properties:CBCharacteristicPropertyRead value:nil permissions:CBAttributePermissionsReadable];
    module.settingCharacteristics[OmiStorageStatusUUID] = storage;
    __block NSUInteger rejected = 0, resolved = 0, newResolved = 0;
    [module readStorageStatusWithId:a.identifier.UUIDString resolver:^(id value) { resolved++; } rejecter:^(NSString *code, NSString *message, NSError *error) { rejected++; }];
    assert(a.reads == 1 && module.storageResolve != nil);
    dispatch_block_t oldTimeout = timers.lastObject;
#if OMI_TEST_IOS_SOURCE
    [module beginConnection:b.identifier.UUIDString recovering:NO restoring:NO resolver:^(id value) {} rejecter:^(NSString *code, NSString *message, NSError *error) { abort(); }];
#else
    [module beginConnection:b.identifier.UUIDString recovering:NO resolver:^(id value) {} rejecter:^(NSString *code, NSString *message, NSError *error) { abort(); }];
#endif
    assert(central.connects == 1 && rejected == 1 && resolved == 0 && module.storageResolve == nil);
    module.connectionState = @"connected";
    module.devices[b.identifier.UUIDString] = [@{@"features":@64} mutableCopy];
    module.settingCharacteristics[OmiStorageStatusUUID] = storage;
    [module readStorageStatusWithId:b.identifier.UUIDString resolver:^(id value) { newResolved++; } rejecter:^(NSString *code, NSString *message, NSError *error) { abort(); }];
    assert(b.reads == 1 && module.storageResolve != nil);
    oldTimeout();
    [module peripheral:(CBPeripheral *)a didUpdateValueForCharacteristic:storage error:nil];
    assert(module.connectedPeripheral == (CBPeripheral *)b && module.storageResolve != nil && rejected == 1 && newResolved == 0);
    const uint8_t bytes[16] = {1, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 1, 0, 0, 0};
    storage.value = [NSData dataWithBytes:bytes length:sizeof(bytes)];
    [module peripheral:(CBPeripheral *)b didUpdateValueForCharacteristic:storage error:nil];
    assert(newResolved == 1 && module.storageResolve == nil && rejected == 1);
    oldTimeout();
    assert(module.connectedPeripheral == (CBPeripheral *)b && newResolved == 1);
    // Unknown firmware must never resolve as recording-ready. Exercise the
    // production callback, not only the small codec predicate.
    CBMutableCharacteristic *codec = [[CBMutableCharacteristic alloc] initWithType:[CBUUID UUIDWithString:OmiCodecUUID] properties:CBCharacteristicPropertyRead value:nil permissions:CBAttributePermissionsReadable];
    uint8_t unknown = 99;
    const uint8_t oversized[] = {21, 0};
    for (NSData *value in @[[NSData dataWithBytes:&unknown length:1], NSData.data, [NSData dataWithBytes:oversized length:2]]) {
      module.connectedPeripheral = (CBPeripheral *)b;
      module.connectReject = ^(NSString *code, NSString *message, NSError *error) { rejected++; };
      codec.value = value;
      module.audioNotifying = YES;
      [module peripheral:(CBPeripheral *)b didUpdateValueForCharacteristic:codec error:nil];
      assert(module.connectedPeripheral == nil && module.codec == nil && !module.audioNotifying);
    }
    assert(rejected == 4);
#if OMI_TEST_IOS_SOURCE
    // A legacy account with no saved capture grant cannot resume. The exact
    // authorized device can restore even with no JS event observer present.
    TestPeripheral *restored = [TestPeripheral new]; restored.identifier = NSUUID.UUID; restored.state = CBPeripheralStateConnected;
    [module centralManager:(CBCentralManager *)central willRestoreState:@{CBCentralManagerRestoredStatePeripheralsKey:@[restored]}];
    assert(module.connectedPeripheral == nil && restored.discoveries == 0);
    restorableDevice = restored.identifier.UUIDString;
    [module centralManager:(CBCentralManager *)central willRestoreState:@{CBCentralManagerRestoredStatePeripheralsKey:@[a, restored]}];
    assert(module.connectedPeripheral == (CBPeripheral *)restored && restored.discoveries == 1);
    module.audioNotifying = YES;
    uint8_t supported = 21;
    codec.value = [NSData dataWithBytes:&supported length:1];
    [module peripheral:(CBPeripheral *)restored didUpdateValueForCharacteristic:codec error:nil];
    assert(module.codec.intValue == 21);
    CBMutableCharacteristic *audio = [[CBMutableCharacteristic alloc] initWithType:[CBUUID UUIDWithString:OmiAudioUUID] properties:CBCharacteristicPropertyNotify value:nil permissions:CBAttributePermissionsReadable];
    const uint8_t frame[] = {9, 0, 0, 42};
    audio.value = [NSData dataWithBytes:frame length:sizeof(frame)];
    assert(!module.observing);
    [module peripheral:(CBPeripheral *)restored didUpdateValueForCharacteristic:audio error:nil];
    assert(nativeAppends == 1 && module.connectedPeripheral == (CBPeripheral *)restored);
    nativeStorageFails = YES;
    [module peripheral:(CBPeripheral *)restored didUpdateValueForCharacteristic:audio error:nil];
    assert(nativeAppends == 2 && module.connectedPeripheral == nil && !module.audioNotifying);
    [module invalidate];
    [module centralManager:(CBCentralManager *)central willRestoreState:@{CBCentralManagerRestoredStatePeripheralsKey:@[restored]}];
    assert(module.connectedPeripheral == nil && module.restoredPeripherals == nil && restored.discoveries == 1);
#endif
    [timers removeAllObjects];
    puts("Apple production BLE: queue ownership, codec rejection, replacement and native restoration/capture passed");
  }
}
