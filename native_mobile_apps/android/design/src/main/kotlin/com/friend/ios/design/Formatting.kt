package com.friend.ios.design

import android.text.format.DateFormat
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Foundation's `Date.formatted(...)` styles, with the same per-locale skeletons. */
object Formatted {
    /** `.formatted(date: .abbreviated, time: .omitted)`: "Oct 8, 2026", "8. Okt. 2026". */
    fun abbreviatedDate(instant: Instant, locale: Locale = Locale.getDefault(), zone: ZoneId = ZoneId.systemDefault()): String =
        skeleton("yMMMd", locale).format(instant.atZone(zone))

    /** `.formatted(date: .omitted, time: .shortened)`: "9:41 AM", "09:41". */
    fun shortTime(instant: Instant, locale: Locale = Locale.getDefault(), zone: ZoneId = ZoneId.systemDefault()): String =
        DateTimeFormatter.ofLocalizedTime(java.time.format.FormatStyle.SHORT).withLocale(locale).format(instant.atZone(zone))

    private val cache = HashMap<Pair<String, Locale>, DateTimeFormatter>()

    private fun skeleton(skeleton: String, locale: Locale): DateTimeFormatter = synchronized(cache) {
        cache.getOrPut(skeleton to locale) { DateTimeFormatter.ofPattern(DateFormat.getBestDateTimePattern(locale, skeleton), locale) }
    }
}
