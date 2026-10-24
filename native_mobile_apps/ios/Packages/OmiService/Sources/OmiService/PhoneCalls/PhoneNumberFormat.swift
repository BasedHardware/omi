import Foundation

/// Dialing rules shared by number setup and the keypad (Flutter `phone_calls_page.dart`
/// `_makeCall` / `_extractCountryCode`, `phone_setup_number_page.dart`).
public enum PhoneNumberFormat {
    /// Spaces, dashes, parentheses and dots, as contacts format numbers.
    public static func stripped(_ raw: String) -> String {
        raw.replacingOccurrences(of: #"[\s\-().]+"#, with: "", options: .regularExpression)
    }

    /// What the keypad dials: a number without `+` gets the country code of the caller's own number
    /// (Flutter prepends it as typed; the trunk 0 is dropped here so `030 …` dials Berlin).
    public static func dialable(_ raw: String, callerNumber: String?) -> String {
        var number = stripped(raw)
        if number.hasPrefix("00") { return "+" + number.dropFirst(2) }
        guard !number.hasPrefix("+"), let callerNumber, let code = callingCode(ofE164: callerNumber) else { return number }
        // A national trunk 0 ("030 …") does not belong after the country code (Italy keeps it).
        if number.hasPrefix("0"), code != "39" { number.removeFirst() }
        return "+" + code + number
    }

    /// The calling code an E.164 number starts with (`+4915…` → `49`), longest known code first.
    public static func callingCode(ofE164 number: String) -> String? {
        guard number.hasPrefix("+") else { return nil }
        let digits = number.dropFirst()
        for length in stride(from: 3, through: 1, by: -1) where digits.count > length {
            let candidate = String(digits.prefix(length))
            if CallingCodes.known.contains(candidate) { return candidate }
        }
        return nil
    }

    /// E.164 from a national number typed under a chosen country; `nil` when it cannot be one.
    /// A leading trunk `0` is dropped (except Italy, which keeps it).
    public static func e164(national raw: String, region: String) -> String? {
        var digits = stripped(raw)
        if digits.hasPrefix("+") { return isE164(digits) ? digits : nil }
        if digits.hasPrefix("00") { return e164(national: "+" + digits.dropFirst(2), region: region) }
        guard let code = CallingCodes.byRegion[region.uppercased()], digits.allSatisfy(\.isNumber), !digits.isEmpty else { return nil }
        if digits.hasPrefix("0"), region.uppercased() != "IT" { digits.removeFirst() }
        if code == "1", digits.count == 11, digits.hasPrefix("1") { digits.removeFirst() }
        let candidate = "+" + code + digits
        // Shorter than a subscriber number anywhere is a typo, not a number.
        return digits.count >= 6 && isE164(candidate) ? candidate : nil
    }

    /// `^\+[1-9]\d{1,14}$`, the backend's own check.
    public static func isE164(_ number: String) -> Bool {
        number.range(of: #"^\+[1-9]\d{1,14}$"#, options: .regularExpression) != nil
    }

    /// Readable grouping for display (`+1 555 123 4567`); the number stays as dialed.
    public static func display(_ number: String) -> String {
        guard isE164(number), let code = callingCode(ofE164: number) else { return number }
        let rest = Array(number.dropFirst(code.count + 1))
        var groups: [String] = []
        var index = 0
        let sizes = code == "1" && rest.count == 10 ? [3, 3, 4] : [3, 3, 3, 3, 3]
        for size in sizes where index < rest.count {
            groups.append(String(rest[index ..< min(index + size, rest.count)]))
            index += size
        }
        return "+\(code) " + groups.joined(separator: " ")
    }
}

/// ITU calling codes by ISO region (the Flutter app's `IntlCountryData` list).
public enum CallingCodes {
    public static let byRegion: [String: String] = [
        "AF": "93", "AL": "355", "DZ": "213", "AS": "1", "AD": "376", "AO": "244", "AI": "1", "AG": "1", "AR": "54",
        "AM": "374", "AW": "297", "AU": "61", "AT": "43", "AZ": "994", "BS": "1", "BH": "973", "BD": "880", "BB": "1",
        "BY": "375", "BE": "32", "BZ": "501", "BJ": "229", "BM": "1", "BT": "975", "BO": "591", "BA": "387", "BW": "267",
        "BR": "55", "VG": "1", "BN": "673", "BG": "359", "BF": "226", "BI": "257", "KH": "855", "CM": "237", "CA": "1",
        "CV": "238", "KY": "1", "CF": "236", "TD": "235", "CL": "56", "CN": "86", "CO": "57", "KM": "269", "CG": "242",
        "CD": "243", "CK": "682", "CR": "506", "CI": "225", "HR": "385", "CU": "53", "CW": "599", "CY": "357", "CZ": "420",
        "DK": "45", "DJ": "253", "DM": "1", "DO": "1", "EC": "593", "EG": "20", "SV": "503", "GQ": "240", "ER": "291",
        "EE": "372", "SZ": "268", "ET": "251", "FK": "500", "FO": "298", "FJ": "679", "FI": "358", "FR": "33", "GF": "594",
        "PF": "689", "GA": "241", "GM": "220", "GE": "995", "DE": "49", "GH": "233", "GI": "350", "GR": "30", "GL": "299",
        "GD": "1", "GP": "590", "GU": "1", "GT": "502", "GG": "44", "GN": "224", "GW": "245", "GY": "592", "HT": "509",
        "HN": "504", "HK": "852", "HU": "36", "IS": "354", "IN": "91", "ID": "62", "IR": "98", "IQ": "964", "IE": "353",
        "IM": "44", "IL": "972", "IT": "39", "JM": "1", "JP": "81", "JE": "44", "JO": "962", "KZ": "7", "KE": "254",
        "KI": "686", "XK": "383", "KW": "965", "KG": "996", "LA": "856", "LV": "371", "LB": "961", "LS": "266", "LR": "231",
        "LY": "218", "LI": "423", "LT": "370", "LU": "352", "MO": "853", "MG": "261", "MW": "265", "MY": "60", "MV": "960",
        "ML": "223", "MT": "356", "MH": "692", "MQ": "596", "MR": "222", "MU": "230", "YT": "262", "MX": "52", "FM": "691",
        "MD": "373", "MC": "377", "MN": "976", "ME": "382", "MS": "1", "MA": "212", "MZ": "258", "MM": "95", "NA": "264",
        "NR": "674", "NP": "977", "NL": "31", "NC": "687", "NZ": "64", "NI": "505", "NE": "227", "NG": "234", "KP": "850",
        "MK": "389", "MP": "1", "NO": "47", "OM": "968", "PK": "92", "PW": "680", "PS": "970", "PA": "507", "PG": "675",
        "PY": "595", "PE": "51", "PH": "63", "PL": "48", "PT": "351", "PR": "1", "QA": "974", "RE": "262", "RO": "40",
        "RU": "7", "RW": "250", "KN": "1", "LC": "1", "VC": "1", "WS": "685", "SM": "378", "ST": "239", "SA": "966",
        "SN": "221", "RS": "381", "SC": "248", "SL": "232", "SG": "65", "SX": "1", "SK": "421", "SI": "386", "SB": "677",
        "SO": "252", "ZA": "27", "KR": "82", "SS": "211", "ES": "34", "LK": "94", "SD": "249", "SR": "597", "SE": "46",
        "CH": "41", "SY": "963", "TW": "886", "TJ": "992", "TZ": "255", "TH": "66", "TL": "670", "TG": "228", "TO": "676",
        "TT": "1", "TN": "216", "TR": "90", "TM": "993", "TC": "1", "TV": "688", "UG": "256", "UA": "380", "AE": "971",
        "GB": "44", "US": "1", "UY": "598", "VI": "1", "UZ": "998", "VU": "678", "VA": "39", "VE": "58", "VN": "84",
        "WF": "681", "YE": "967", "ZM": "260", "ZW": "263",
    ]

    public static let known: Set<String> = Set(byRegion.values)
}
