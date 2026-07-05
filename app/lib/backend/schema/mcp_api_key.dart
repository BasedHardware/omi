// Phase 4 SSOT: hand-written schema classes replaced with generated wire DTOs.
// The generated types carry identical fields + fromJson + toJson; the hand-written
// classes were pure 1:1 field-mapping boilerplate (fromGenerated/toGenerated).
import 'package:omi/backend/schema/gen/api_keys_wire.g.dart' as wire;

typedef McpApiKey = wire.GeneratedMcpApiKey;
typedef McpApiKeyCreated = wire.GeneratedMcpApiKeyCreated;
