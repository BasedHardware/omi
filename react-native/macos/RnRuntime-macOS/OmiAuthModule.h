#import <React/RCTBridgeModule.h>

BOOL OmiAuthEnvironmentCloudTokensIgnored(void);
void OmiAuthSetEnvironmentCloudTokensIgnored(BOOL ignored);
BOOL OmiAuthShippingSessionIgnored(void);
void OmiAuthSetShippingSessionIgnored(BOOL ignored);
BOOL OmiAuthImportShippingSessionIfNeeded(void);

@interface OmiAuthModule : NSObject <RCTBridgeModule>
@end
