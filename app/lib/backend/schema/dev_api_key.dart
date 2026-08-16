// Phase 4 SSOT: hand-written schema classes replaced with generated wire DTOs.
// The generated types carry identical fields + fromJson + toJson; the hand-written
// classes were pure 1:1 field-mapping boilerplate (fromGenerated/toGenerated).
//
// Note: DevApiKeyCreated previously extended DevApiKey for list-polymorphism. The
// generated wire types are siblings without inheritance, so callers that insert a
// DevApiKeyCreated into a List<DevApiKey> convert explicitly via
// DevApiKey.fromJson(created.toJson()) (the round-trip drops the one-off `key`).
import 'package:omi/backend/schema/gen/api_keys_wire.g.dart' as wire;

typedef DevApiKey = wire.GeneratedDevApiKey;
typedef DevApiKeyCreated = wire.GeneratedDevApiKeyCreated;
