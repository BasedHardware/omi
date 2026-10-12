import Foundation

/// Compares Messages addresses the way people write them and the way Messages
/// stores them.
///
/// Contacts often spells a number "(415) 555-0123" or "07700 900123", while
/// Messages stores "+14155550123" or "+447700900123". Two numbers name the same
/// handle only when:
/// - both are international (`+`, `00`, or `011` in North America) with equal
///   digits, or both are national with equal digits; or
/// - one is international and the other is the national form of that number in
///   the Mac's own region: the region's calling code followed by the national
///   digits, as written or without the region's trunk prefix ("0" in most
///   places, "8" in Russia and some neighbours, "8 0" in Belarus, "06" in
///   Hungary, "1" in North America).
///
/// Two different international numbers never match, however their digits
/// overlap, so "+14155550123" and "+914155550123" stay two people. With no
/// region set (or the "World" region), a national number never matches an
/// international one. Extensions ("ext. 45", ";45") and a "(0)" written inside
/// an international number ("+44 (0) 7700 900123") are ignored. Argentine
/// mobiles written nationally with the "15" mobile prefix are not rewritten to
/// the international "9" form, so they do not match.
enum MessagingHandle {
  /// The region this Mac is set to, such as "US"; nil when unset.
  static func currentRegion() -> String? {
    Locale.current.region?.identifier
  }

  static func isSame(_ stored: String, _ requested: String, region: String?) -> Bool {
    guard let left = Parsed(stored, region: region), let right = Parsed(requested, region: region) else {
      return false
    }
    switch (left, right) {
    case (.email(let a), .email(let b)):
      return a == b
    case (.phone(let a), .phone(let b)):
      if a.isInternational == b.isInternational { return a.digits == b.digits }
      let international = a.isInternational ? a : b
      let national = a.isInternational ? b : a
      return internationalForms(ofNational: national.digits, region: region).contains(international.digits)
    default:
      return false
    }
  }

  /// One key per distinct address, so callers can tell when a request matched
  /// two different stored numbers (an Italian "06 1234 5678" against both
  /// "+390612345678" and "+39612345678").
  static func identityKey(_ handle: String, region: String?) -> String? {
    switch Parsed(handle, region: region) {
    case .email(let address): return "email:" + address
    case .phone(let number):
      if number.isInternational { return "intl:" + number.digits }
      let forms = internationalForms(ofNational: number.digits, region: region).sorted()
      return forms.count == 1 ? "intl:" + forms[0] : "national:" + number.digits
    case nil: return nil
    }
  }

  /// The international digit strings a national number can stand for in a region.
  private static func internationalForms(ofNational national: String, region: String?) -> Set<String> {
    guard let region, let callingCode = callingCode(forRegion: region) else { return [] }
    var forms: Set<String> = [callingCode + national]
    for trunk in trunkPrefixes(forRegion: region) where national.hasPrefix(trunk) {
      forms.insert(callingCode + String(national.dropFirst(trunk.count)))
    }
    return forms
  }

  /// National trunk prefixes, dropped when a number is dialled from abroad.
  static func trunkPrefixes(forRegion region: String) -> [String] {
    switch region.uppercased() {
    case "RU", "KZ", "TJ", "TM": return ["8"]
    case "BY": return ["80", "8"]
    case "LT": return ["8", "0"]
    case "HU": return ["06"]
    case _ where callingCode(forRegion: region) == "1": return ["1"]
    default: return ["0"]
    }
  }

  private enum Parsed {
    case email(String)
    case phone(Number)

    struct Number {
      let digits: String
      let isInternational: Bool
    }

    init?(_ raw: String, region: String?) {
      var handle = raw.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !handle.isEmpty else { return nil }
      if handle.contains("@") {
        self = .email(handle.lowercased())
        return
      }
      if let ext = handle.range(of: #"(?i)\s*(?:;|,|#|ext\.?|extension|x)\s*\d+\s*$"#, options: .regularExpression) {
        handle.removeSubrange(ext)
      }
      let northAmerican = region.flatMap(MessagingHandle.callingCode(forRegion:)) == "1"
      func digits(of text: String) -> String { String(text.filter { $0.isASCII && $0.isNumber }) }
      let written = digits(of: handle)
      let isInternational =
        handle.hasPrefix("+") || written.hasPrefix("00") || (northAmerican && written.hasPrefix("011"))
      if isInternational {
        // "+44 (0) 7700 900123": the bracketed 0 is the national trunk prefix.
        handle = handle.replacingOccurrences(of: #"\(\s*0\s*\)"#, with: "", options: .regularExpression)
      }
      var number = digits(of: handle)
      if !handle.hasPrefix("+") {
        if number.hasPrefix("00") {
          number.removeFirst(2)
        } else if northAmerican, number.hasPrefix("011") {
          number.removeFirst(3)
        }
      }
      guard !number.isEmpty else { return nil }
      self = .phone(Number(digits: number, isInternational: isInternational))
    }
  }

  /// ITU-T E.164 country calling codes by ISO 3166 region. Regions without one
  /// (uninhabited territories, "001" for the World) return nil.
  static func callingCode(forRegion region: String) -> String? {
    switch region.uppercased() {
    case "US", "CA", "AG", "AI", "AS", "BB", "BM", "BS", "DM", "DO", "GD", "GU", "JM", "KN", "KY", "LC", "MP", "MS",
      "PR", "SX", "TC", "TT", "VC", "VG", "VI":
      return "1"
    case "RU", "KZ": return "7"
    case "EG": return "20"
    case "ZA": return "27"
    case "GR": return "30"
    case "NL": return "31"
    case "BE": return "32"
    case "FR": return "33"
    case "ES", "EA", "IC": return "34"
    case "HU": return "36"
    case "IT", "VA": return "39"
    case "RO": return "40"
    case "CH": return "41"
    case "AT": return "43"
    case "GB", "GG", "IM", "JE": return "44"
    case "DK": return "45"
    case "SE": return "46"
    case "NO", "SJ": return "47"
    case "PL": return "48"
    case "DE": return "49"
    case "PE": return "51"
    case "MX": return "52"
    case "CU": return "53"
    case "AR": return "54"
    case "BR": return "55"
    case "CL": return "56"
    case "CO": return "57"
    case "VE": return "58"
    case "MY": return "60"
    case "AU", "CX", "CC": return "61"
    case "ID": return "62"
    case "PH": return "63"
    case "NZ", "PN": return "64"
    case "SG": return "65"
    case "TH": return "66"
    case "JP": return "81"
    case "KR": return "82"
    case "VN": return "84"
    case "CN": return "86"
    case "TR": return "90"
    case "IN": return "91"
    case "PK": return "92"
    case "AF": return "93"
    case "LK": return "94"
    case "MM": return "95"
    case "IR": return "98"
    case "AC": return "247"
    case "SS": return "211"
    case "MA", "EH": return "212"
    case "DZ": return "213"
    case "TN": return "216"
    case "LY": return "218"
    case "GM": return "220"
    case "SN": return "221"
    case "MR": return "222"
    case "ML": return "223"
    case "GN": return "224"
    case "CI": return "225"
    case "BF": return "226"
    case "NE": return "227"
    case "TG": return "228"
    case "BJ": return "229"
    case "MU": return "230"
    case "LR": return "231"
    case "SL": return "232"
    case "GH": return "233"
    case "NG": return "234"
    case "TD": return "235"
    case "CF": return "236"
    case "CM": return "237"
    case "CV": return "238"
    case "ST": return "239"
    case "GQ": return "240"
    case "GA": return "241"
    case "CG": return "242"
    case "CD": return "243"
    case "AO": return "244"
    case "GW": return "245"
    case "IO", "DG": return "246"
    case "SC": return "248"
    case "SD": return "249"
    case "RW": return "250"
    case "ET": return "251"
    case "SO": return "252"
    case "DJ": return "253"
    case "KE": return "254"
    case "TZ": return "255"
    case "UG": return "256"
    case "BI": return "257"
    case "MZ": return "258"
    case "ZM": return "260"
    case "MG": return "261"
    case "RE", "YT", "TF": return "262"
    case "ZW": return "263"
    case "NA": return "264"
    case "MW": return "265"
    case "LS": return "266"
    case "BW": return "267"
    case "SZ": return "268"
    case "KM": return "269"
    case "SH", "TA": return "290"
    case "ER": return "291"
    case "AW": return "297"
    case "FO": return "298"
    case "GL": return "299"
    case "GI": return "350"
    case "PT": return "351"
    case "LU": return "352"
    case "IE": return "353"
    case "IS": return "354"
    case "AL": return "355"
    case "MT": return "356"
    case "CY": return "357"
    case "FI", "AX": return "358"
    case "BG": return "359"
    case "LT": return "370"
    case "LV": return "371"
    case "EE": return "372"
    case "MD": return "373"
    case "AM": return "374"
    case "BY": return "375"
    case "AD": return "376"
    case "MC": return "377"
    case "SM": return "378"
    case "UA": return "380"
    case "RS": return "381"
    case "ME": return "382"
    case "XK": return "383"
    case "HR": return "385"
    case "SI": return "386"
    case "BA": return "387"
    case "MK": return "389"
    case "CZ": return "420"
    case "SK": return "421"
    case "LI": return "423"
    case "FK", "GS": return "500"
    case "BZ": return "501"
    case "GT": return "502"
    case "SV": return "503"
    case "HN": return "504"
    case "NI": return "505"
    case "CR": return "506"
    case "PA": return "507"
    case "PM": return "508"
    case "HT": return "509"
    case "GP", "BL", "MF": return "590"
    case "BO": return "591"
    case "GY": return "592"
    case "EC": return "593"
    case "GF": return "594"
    case "PY": return "595"
    case "MQ": return "596"
    case "SR": return "597"
    case "UY": return "598"
    case "CW", "BQ": return "599"
    case "TL": return "670"
    case "NF", "AQ": return "672"
    case "BN": return "673"
    case "NR": return "674"
    case "PG": return "675"
    case "TO": return "676"
    case "SB": return "677"
    case "VU": return "678"
    case "FJ": return "679"
    case "PW": return "680"
    case "WF": return "681"
    case "CK": return "682"
    case "NU": return "683"
    case "WS": return "685"
    case "KI": return "686"
    case "NC": return "687"
    case "TV": return "688"
    case "PF": return "689"
    case "TK": return "690"
    case "FM": return "691"
    case "MH": return "692"
    case "KP": return "850"
    case "HK": return "852"
    case "MO": return "853"
    case "KH": return "855"
    case "LA": return "856"
    case "BD": return "880"
    case "TW": return "886"
    case "MV": return "960"
    case "LB": return "961"
    case "JO": return "962"
    case "SY": return "963"
    case "IQ": return "964"
    case "KW": return "965"
    case "SA": return "966"
    case "YE": return "967"
    case "OM": return "968"
    case "PS": return "970"
    case "AE": return "971"
    case "IL": return "972"
    case "BH": return "973"
    case "QA": return "974"
    case "BT": return "975"
    case "MN": return "976"
    case "NP": return "977"
    case "TJ": return "992"
    case "TM": return "993"
    case "AZ": return "994"
    case "GE": return "995"
    case "KG": return "996"
    case "UZ": return "998"
    default: return nil
    }
  }
}
