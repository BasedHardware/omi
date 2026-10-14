package com.friend.ios.network.generated

import kotlinx.serialization.json.Json

/**
 * Json configuration for the generated OmiAPI DTOs. Tolerant like the Swift
 * decoders: unknown keys are ignored (the backend adds fields), nulls are not
 * encoded for nullable properties (Swift `encodeIfPresent`).
 */
val OmiJson: Json = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
    isLenient = true
}
