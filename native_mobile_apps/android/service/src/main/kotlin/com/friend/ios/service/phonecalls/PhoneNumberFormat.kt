package com.friend.ios.service.phonecalls

/**
 * Port of `PhoneNumberFormat.swift`. Dialing rules shared by number setup and the keypad (Flutter
 * `phone_calls_page.dart` `_makeCall` / `_extractCountryCode`, `phone_setup_number_page.dart`).
 */
object PhoneNumberFormat {
    private val separators = Regex("""[\s\-().]+""")
    private val e164Pattern = Regex("""^\+[1-9]\d{1,14}$""")

    /** Spaces, dashes, parentheses and dots, as contacts format numbers. */
    fun stripped(raw: String): String = raw.replace(separators, "")

    /**
     * What the keypad dials: a number without `+` gets the country code of the caller's own number
     * (Flutter prepends it as typed; the trunk 0 is dropped here so `030 ...` dials Berlin).
     */
    fun dialable(raw: String, callerNumber: String?): String {
        var number = stripped(raw)
        if (number.startsWith("00")) return "+" + number.drop(2)
        if (number.startsWith("+") || callerNumber == null) return number
        val code = callingCode(ofE164 = callerNumber) ?: return number
        // A national trunk 0 ("030 ...") does not belong after the country code (Italy keeps it).
        if (number.startsWith("0") && code != "39") number = number.drop(1)
        return "+$code$number"
    }

    /** The calling code an E.164 number starts with (`+4915...` -> `49`), longest known code first. */
    fun callingCode(ofE164: String): String? {
        if (!ofE164.startsWith("+")) return null
        val digits = ofE164.drop(1)
        for (length in 3 downTo 1) {
            if (digits.length <= length) continue
            val candidate = digits.take(length)
            if (candidate in CallingCodes.known) return candidate
        }
        return null
    }

    /**
     * E.164 from a national number typed under a chosen country; null when it cannot be one.
     * A leading trunk `0` is dropped (except Italy, which keeps it).
     */
    fun e164(national: String, region: String): String? {
        var digits = stripped(national)
        if (digits.startsWith("+")) return if (isE164(digits)) digits else null
        if (digits.startsWith("00")) return e164("+" + digits.drop(2), region)
        val code = CallingCodes.byRegion[region.uppercase()] ?: return null
        if (digits.isEmpty() || !digits.all { it.isDigit() }) return null
        if (digits.startsWith("0") && region.uppercase() != "IT") digits = digits.drop(1)
        if (code == "1" && digits.length == 11 && digits.startsWith("1")) digits = digits.drop(1)
        val candidate = "+$code$digits"
        // Shorter than a subscriber number anywhere is a typo, not a number.
        return if (digits.length >= 6 && isE164(candidate)) candidate else null
    }

    /** `^\+[1-9]\d{1,14}$`, the backend's own check. */
    fun isE164(number: String): Boolean = e164Pattern.matches(number)

    /** Readable grouping for display (`+1 555 123 4567`); the number stays as dialed. */
    fun display(number: String): String {
        if (!isE164(number)) return number
        val code = callingCode(ofE164 = number) ?: return number
        val rest = number.drop(code.length + 1)
        val sizes = if (code == "1" && rest.length == 10) listOf(3, 3, 4) else listOf(3, 3, 3, 3, 3)
        val groups = mutableListOf<String>()
        var index = 0
        for (size in sizes) {
            if (index >= rest.length) break
            groups += rest.substring(index, minOf(index + size, rest.length))
            index += size
        }
        return "+$code " + groups.joinToString(" ")
    }
}

/** ITU calling codes by ISO region (the Flutter app's `IntlCountryData` list). */
object CallingCodes {
    val byRegion: Map<String, String> = mapOf(
        "AF" to "93", "AL" to "355", "DZ" to "213", "AS" to "1", "AD" to "376", "AO" to "244", "AI" to "1", "AG" to "1", "AR" to "54",
        "AM" to "374", "AW" to "297", "AU" to "61", "AT" to "43", "AZ" to "994", "BS" to "1", "BH" to "973", "BD" to "880", "BB" to "1",
        "BY" to "375", "BE" to "32", "BZ" to "501", "BJ" to "229", "BM" to "1", "BT" to "975", "BO" to "591", "BA" to "387", "BW" to "267",
        "BR" to "55", "VG" to "1", "BN" to "673", "BG" to "359", "BF" to "226", "BI" to "257", "KH" to "855", "CM" to "237", "CA" to "1",
        "CV" to "238", "KY" to "1", "CF" to "236", "TD" to "235", "CL" to "56", "CN" to "86", "CO" to "57", "KM" to "269", "CG" to "242",
        "CD" to "243", "CK" to "682", "CR" to "506", "CI" to "225", "HR" to "385", "CU" to "53", "CW" to "599", "CY" to "357", "CZ" to "420",
        "DK" to "45", "DJ" to "253", "DM" to "1", "DO" to "1", "EC" to "593", "EG" to "20", "SV" to "503", "GQ" to "240", "ER" to "291",
        "EE" to "372", "SZ" to "268", "ET" to "251", "FK" to "500", "FO" to "298", "FJ" to "679", "FI" to "358", "FR" to "33", "GF" to "594",
        "PF" to "689", "GA" to "241", "GM" to "220", "GE" to "995", "DE" to "49", "GH" to "233", "GI" to "350", "GR" to "30", "GL" to "299",
        "GD" to "1", "GP" to "590", "GU" to "1", "GT" to "502", "GG" to "44", "GN" to "224", "GW" to "245", "GY" to "592", "HT" to "509",
        "HN" to "504", "HK" to "852", "HU" to "36", "IS" to "354", "IN" to "91", "ID" to "62", "IR" to "98", "IQ" to "964", "IE" to "353",
        "IM" to "44", "IL" to "972", "IT" to "39", "JM" to "1", "JP" to "81", "JE" to "44", "JO" to "962", "KZ" to "7", "KE" to "254",
        "KI" to "686", "XK" to "383", "KW" to "965", "KG" to "996", "LA" to "856", "LV" to "371", "LB" to "961", "LS" to "266", "LR" to "231",
        "LY" to "218", "LI" to "423", "LT" to "370", "LU" to "352", "MO" to "853", "MG" to "261", "MW" to "265", "MY" to "60", "MV" to "960",
        "ML" to "223", "MT" to "356", "MH" to "692", "MQ" to "596", "MR" to "222", "MU" to "230", "YT" to "262", "MX" to "52", "FM" to "691",
        "MD" to "373", "MC" to "377", "MN" to "976", "ME" to "382", "MS" to "1", "MA" to "212", "MZ" to "258", "MM" to "95", "NA" to "264",
        "NR" to "674", "NP" to "977", "NL" to "31", "NC" to "687", "NZ" to "64", "NI" to "505", "NE" to "227", "NG" to "234", "KP" to "850",
        "MK" to "389", "MP" to "1", "NO" to "47", "OM" to "968", "PK" to "92", "PW" to "680", "PS" to "970", "PA" to "507", "PG" to "675",
        "PY" to "595", "PE" to "51", "PH" to "63", "PL" to "48", "PT" to "351", "PR" to "1", "QA" to "974", "RE" to "262", "RO" to "40",
        "RU" to "7", "RW" to "250", "KN" to "1", "LC" to "1", "VC" to "1", "WS" to "685", "SM" to "378", "ST" to "239", "SA" to "966",
        "SN" to "221", "RS" to "381", "SC" to "248", "SL" to "232", "SG" to "65", "SX" to "1", "SK" to "421", "SI" to "386", "SB" to "677",
        "SO" to "252", "ZA" to "27", "KR" to "82", "SS" to "211", "ES" to "34", "LK" to "94", "SD" to "249", "SR" to "597", "SE" to "46",
        "CH" to "41", "SY" to "963", "TW" to "886", "TJ" to "992", "TZ" to "255", "TH" to "66", "TL" to "670", "TG" to "228", "TO" to "676",
        "TT" to "1", "TN" to "216", "TR" to "90", "TM" to "993", "TC" to "1", "TV" to "688", "UG" to "256", "UA" to "380", "AE" to "971",
        "GB" to "44", "US" to "1", "UY" to "598", "VI" to "1", "UZ" to "998", "VU" to "678", "VA" to "39", "VE" to "58", "VN" to "84",
        "WF" to "681", "YE" to "967", "ZM" to "260", "ZW" to "263",
    )

    val known: Set<String> = byRegion.values.toSet()
}
