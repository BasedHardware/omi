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
@implementation OmiBackendModule
- (void)rememberedDevice:(NSString *)action device:(NSDictionary *)device current:(BOOL (^)(void))current resolver:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject { abort(); }
@end

@interface TestPeripheral : NSObject
@property(nonatomic, strong) NSUUID *identifier;
@property(nonatomic, weak) id delegate;
@property(nonatomic) CBPeripheralState state;
@property(nonatomic) NSUInteger reads;
- (void)readValueForCharacteristic:(CBCharacteristic *)characteristic;
@end
@implementation TestPeripheral
- (void)readValueForCharacteristic:(CBCharacteristic *)characteristic { self.reads++; }
@end
@interface TestCentral : NSObject
@property(nonatomic, weak) id delegate;
@property(nonatomic) CBManagerState state;
@property(nonatomic) NSUInteger connects;
- (void)stopScan;
- (void)cancelPeripheralConnection:(CBPeripheral *)peripheral;
- (void)connectPeripheral:(CBPeripheral *)peripheral options:(NSDictionary *)options;
@end
@implementation TestCentral
- (void)stopScan {}
- (void)cancelPeripheralConnection:(CBPeripheral *)peripheral {}
- (void)connectPeripheral:(CBPeripheral *)peripheral options:(NSDictionary *)options { self.connects++; }
@end

int main() {
  @autoreleasepool {
    timers = [NSMutableArray array];
    OmiNativeModule *module = [OmiNativeModule new];
    TestCentral *central = [TestCentral new]; central.state = CBManagerStatePoweredOn;
    module.central = (CBCentralManager *)central;
    TestPeripheral *a = [TestPeripheral new]; a.identifier = NSUUID.UUID; a.state = CBPeripheralStateConnected;
    TestPeripheral *b = [TestPeripheral new]; b.identifier = NSUUID.UUID; b.state = CBPeripheralStateConnected;
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
    [module beginConnection:b.identifier.UUIDString recovering:NO resolver:^(id value) {} rejecter:^(NSString *code, NSString *message, NSError *error) { abort(); }];
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
    [timers removeAllObjects];
    puts("Apple production connection replacement settles storage and fences stale callbacks");
  }
}
