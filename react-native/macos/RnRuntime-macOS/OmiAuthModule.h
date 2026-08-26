#import <React/RCTBridgeModule.h>

BOOL OmiAuthEnvironmentCloudTokensIgnored(void);
void OmiAuthSetEnvironmentCloudTokensIgnored(BOOL ignored);

@interface OmiAuthModule : NSObject <RCTBridgeModule>
@end
