package com.friend.ios.network.generated

import kotlinx.serialization.KSerializer
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder

/**
 * A string-backed enum mirroring a Swift `enum X: String` (`rawValue`).
 * Every generated OmiAPI enum implements it and has an `_unknown` case.
 */
interface OmiRawEnum {
    val rawValue: String
}

/**
 * Reusable serializer for generated string enums: encodes `rawValue`, decodes any
 * value it does not know to [unknown] instead of throwing (Swift: `?? ._unknown`).
 */
open class OmiRawEnumSerializer<E>(
    serialName: String,
    values: List<E>,
    private val unknown: E,
) : KSerializer<E> where E : Enum<E>, E : OmiRawEnum {
    private val byRawValue: Map<String, E> = values.associateBy { it.rawValue }

    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor(serialName, PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): E = byRawValue[decoder.decodeString()] ?: unknown

    override fun serialize(encoder: Encoder, value: E) = encoder.encodeString(value.rawValue)
}

/** Swift `X(rawValue: raw)`: the case with that raw value, or null. */
inline fun <reified E> omiRawEnumOf(raw: String): E? where E : Enum<E>, E : OmiRawEnum =
    enumValues<E>().firstOrNull { it.rawValue == raw }
