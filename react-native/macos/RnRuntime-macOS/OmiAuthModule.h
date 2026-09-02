#import <React/RCTBridgeModule.h>

BOOL OmiAuthEnvironmentCloudTokensIgnored(void);
void OmiAuthSetEnvironmentCloudTokensIgnored(BOOL ignored);
BOOL OmiAuthShippingSessionIgnored(void);
void OmiAuthSetShippingSessionIgnored(BOOL ignored);
BOOL OmiAuthImportShippingSessionIfNeeded(void);
// The public Firebase Web API key used to mint this app's sessions. Refresh
// always has it available; /v1/config/api-keys requires a cloud session and
// 401s, so it must never be a refresh dependency.
NSString *OmiAuthResolvedFirebaseApiKey(void);

@interface OmiAuthModule : NSObject <RCTBridgeModule>
@end
