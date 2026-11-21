import Foundation
import OmiSupport

/// Compares Messages addresses the way people write them and the way Messages
/// stores them.
///
/// Contacts often spells a number "(267) 361-8369" or "07700 900123", while
/// Messages stores "+12673618369" or "+447700900123". Two numbers name the same
/// handle only when:
/// - both are international (`+`, `00`, or `011` in North America) with equal
///   digits, or both are national with equal digits; or
/// - one is international and the other is a national number that, after an
///   optional trunk prefix ("0" in most places, "8" in Russia and some
///   neighbours, "8 0" in Belarus, "06" in Hungary, "1" in North America), is
///   that international number without a real calling code.
///
/// Which calling codes count: when the chat's sending account is a phone
/// number (`chat.account_login` "P:+1…"), only that account's code, because
/// Messages resolves a national number through the account. Otherwise every
/// code in the ITU table counts, the Mac's region included but not preferred:
/// a person in India texting a US number typed nationally is resolved by
/// Messages to +1, not +91. Callers treat a request that matches two different
/// stored numbers as ambiguous rather than picking one.
///
/// Two different international numbers never match, however their digits
/// overlap, so "+14155550123" and "+914155550123" stay two people. Extensions
/// ("ext. 45", ";45") and a "(0)" written inside an international number
/// ("+44 (0) 7700 900123") are ignored. Argentine mobiles written nationally
/// with the "15" mobile prefix are not rewritten to the international "9"
/// form, so they do not match.
enum MessagingHandle {
  /// The region this Mac is set to, such as "US"; nil when unset. It decides
  /// only whether "011" starts an international number.
  static func currentRegion() -> String? {
    Locale.current.region?.identifier
  }

  /// Every calling code in the table.
  static let allCallingCodes: Set<String> = Set(callingCodeTable.map(\.code))

  static func isSame(_ stored: String, _ requested: String, region: String?, accountLogin: String? = nil) -> Bool {
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
      let codes = accountCallingCode(accountLogin).map { Set([$0]) } ?? allCallingCodes
      return isInternational(international.digits, nationalForm: national.digits, callingCodes: codes)
    default:
      return false
    }
  }

  /// Whether the stored addresses a request matched name more than one
  /// person: two that are not the same handle as each other.
  static func containsDistinctAddresses(_ handles: [String], region: String?) -> Bool {
    for (index, first) in handles.enumerated() {
      for second in handles[(index + 1)...] where !isSame(first, second, region: region) {
        return true
      }
    }
    return false
  }

  /// The calling code of a phone-number sending account ("P:+12673618369" →
  /// "1"); nil for an email account or anything unreadable.
  static func accountCallingCode(_ login: String?) -> String? {
    guard let login, login.lowercased().hasPrefix("p:") else { return nil }
    let number = login.dropFirst(2).trimmingCharacters(in: .whitespaces)
    guard number.hasPrefix("+") else { return nil }
    let digits = String(number.filter { $0.isASCII && $0.isNumber })
    // E.164 calling codes are prefix-free, so the first that fits is the one.
    for length in 1...3 where digits.count > length {
      let candidate = String(digits.prefix(length))
      if allCallingCodes.contains(candidate) { return candidate }
    }
    return nil
  }

  /// Whether `international` is `national` (as written, or without one of its
  /// calling code's trunk prefixes) behind one of `callingCodes`.
  private static func isInternational(
    _ international: String, nationalForm national: String, callingCodes: Set<String>
  ) -> Bool {
    func code(before tail: String) -> String? {
      guard international.count > tail.count, international.hasSuffix(tail) else { return nil }
      let code = String(international.dropLast(tail.count))
      return callingCodes.contains(code) ? code : nil
    }
    if code(before: national) != nil { return true }
    for trunk in ["0", "06", "1", "8", "80"] where national.hasPrefix(trunk) {
      if let code = code(before: String(national.dropFirst(trunk.count))),
        trunkPrefixes(forCallingCode: code).contains(trunk)
      {
        return true
      }
    }
    return false
  }

  /// National trunk prefixes, dropped when a number is dialled from abroad.
  static func trunkPrefixes(forCallingCode callingCode: String) -> [String] {
    switch callingCode {
    case "7", "992", "993": return ["8"]
    case "375": return ["80", "8"]
    case "370": return ["8", "0"]
    case "36": return ["06"]
    case "1": return ["1"]
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

  /// ITU-T E.164 country calling codes and the ISO 3166 regions that use them.
  /// Regions without a code of their own (uninhabited territories, "001" for
  /// the World) are not listed.
  static let callingCodeTable: [(code: String, regions: [String])] = [
    (
      "1",
      [
        "US", "CA", "AG", "AI", "AS", "BB", "BM", "BS", "DM", "DO", "GD", "GU", "JM", "KN", "KY", "LC", "MP", "MS",
        "PR", "SX", "TC", "TT", "VC", "VG", "VI",
      ]
    ),
    ("7", ["RU", "KZ"]),
    ("20", ["EG"]),
    ("27", ["ZA"]),
    ("30", ["GR"]),
    ("31", ["NL"]),
    ("32", ["BE"]),
    ("33", ["FR"]),
    ("34", ["ES", "EA", "IC"]),
    ("36", ["HU"]),
    ("39", ["IT", "VA"]),
    ("40", ["RO"]),
    ("41", ["CH"]),
    ("43", ["AT"]),
    ("44", ["GB", "GG", "IM", "JE"]),
    ("45", ["DK"]),
    ("46", ["SE"]),
    ("47", ["NO", "SJ"]),
    ("48", ["PL"]),
    ("49", ["DE"]),
    ("51", ["PE"]),
    ("52", ["MX"]),
    ("53", ["CU"]),
    ("54", ["AR"]),
    ("55", ["BR"]),
    ("56", ["CL"]),
    ("57", ["CO"]),
    ("58", ["VE"]),
    ("60", ["MY"]),
    ("61", ["AU", "CX", "CC"]),
    ("62", ["ID"]),
    ("63", ["PH"]),
    ("64", ["NZ", "PN"]),
    ("65", ["SG"]),
    ("66", ["TH"]),
    ("81", ["JP"]),
    ("82", ["KR"]),
    ("84", ["VN"]),
    ("86", ["CN"]),
    ("90", ["TR"]),
    ("91", ["IN"]),
    ("92", ["PK"]),
    ("93", ["AF"]),
    ("94", ["LK"]),
    ("95", ["MM"]),
    ("98", ["IR"]),
    ("247", ["AC"]),
    ("211", ["SS"]),
    ("212", ["MA", "EH"]),
    ("213", ["DZ"]),
    ("216", ["TN"]),
    ("218", ["LY"]),
    ("220", ["GM"]),
    ("221", ["SN"]),
    ("222", ["MR"]),
    ("223", ["ML"]),
    ("224", ["GN"]),
    ("225", ["CI"]),
    ("226", ["BF"]),
    ("227", ["NE"]),
    ("228", ["TG"]),
    ("229", ["BJ"]),
    ("230", ["MU"]),
    ("231", ["LR"]),
    ("232", ["SL"]),
    ("233", ["GH"]),
    ("234", ["NG"]),
    ("235", ["TD"]),
    ("236", ["CF"]),
    ("237", ["CM"]),
    ("238", ["CV"]),
    ("239", ["ST"]),
    ("240", ["GQ"]),
    ("241", ["GA"]),
    ("242", ["CG"]),
    ("243", ["CD"]),
    ("244", ["AO"]),
    ("245", ["GW"]),
    ("246", ["IO", "DG"]),
    ("248", ["SC"]),
    ("249", ["SD"]),
    ("250", ["RW"]),
    ("251", ["ET"]),
    ("252", ["SO"]),
    ("253", ["DJ"]),
    ("254", ["KE"]),
    ("255", ["TZ"]),
    ("256", ["UG"]),
    ("257", ["BI"]),
    ("258", ["MZ"]),
    ("260", ["ZM"]),
    ("261", ["MG"]),
    ("262", ["RE", "YT", "TF"]),
    ("263", ["ZW"]),
    ("264", ["NA"]),
    ("265", ["MW"]),
    ("266", ["LS"]),
    ("267", ["BW"]),
    ("268", ["SZ"]),
    ("269", ["KM"]),
    ("290", ["SH", "TA"]),
    ("291", ["ER"]),
    ("297", ["AW"]),
    ("298", ["FO"]),
    ("299", ["GL"]),
    ("350", ["GI"]),
    ("351", ["PT"]),
    ("352", ["LU"]),
    ("353", ["IE"]),
    ("354", ["IS"]),
    ("355", ["AL"]),
    ("356", ["MT"]),
    ("357", ["CY"]),
    ("358", ["FI", "AX"]),
    ("359", ["BG"]),
    ("370", ["LT"]),
    ("371", ["LV"]),
    ("372", ["EE"]),
    ("373", ["MD"]),
    ("374", ["AM"]),
    ("375", ["BY"]),
    ("376", ["AD"]),
    ("377", ["MC"]),
    ("378", ["SM"]),
    ("380", ["UA"]),
    ("381", ["RS"]),
    ("382", ["ME"]),
    ("383", ["XK"]),
    ("385", ["HR"]),
    ("386", ["SI"]),
    ("387", ["BA"]),
    ("389", ["MK"]),
    ("420", ["CZ"]),
    ("421", ["SK"]),
    ("423", ["LI"]),
    ("500", ["FK", "GS"]),
    ("501", ["BZ"]),
    ("502", ["GT"]),
    ("503", ["SV"]),
    ("504", ["HN"]),
    ("505", ["NI"]),
    ("506", ["CR"]),
    ("507", ["PA"]),
    ("508", ["PM"]),
    ("509", ["HT"]),
    ("590", ["GP", "BL", "MF"]),
    ("591", ["BO"]),
    ("592", ["GY"]),
    ("593", ["EC"]),
    ("594", ["GF"]),
    ("595", ["PY"]),
    ("596", ["MQ"]),
    ("597", ["SR"]),
    ("598", ["UY"]),
    ("599", ["CW", "BQ"]),
    ("670", ["TL"]),
    ("672", ["NF", "AQ"]),
    ("673", ["BN"]),
    ("674", ["NR"]),
    ("675", ["PG"]),
    ("676", ["TO"]),
    ("677", ["SB"]),
    ("678", ["VU"]),
    ("679", ["FJ"]),
    ("680", ["PW"]),
    ("681", ["WF"]),
    ("682", ["CK"]),
    ("683", ["NU"]),
    ("685", ["WS"]),
    ("686", ["KI"]),
    ("687", ["NC"]),
    ("688", ["TV"]),
    ("689", ["PF"]),
    ("690", ["TK"]),
    ("691", ["FM"]),
    ("692", ["MH"]),
    ("850", ["KP"]),
    ("852", ["HK"]),
    ("853", ["MO"]),
    ("855", ["KH"]),
    ("856", ["LA"]),
    ("880", ["BD"]),
    ("886", ["TW"]),
    ("960", ["MV"]),
    ("961", ["LB"]),
    ("962", ["JO"]),
    ("963", ["SY"]),
    ("964", ["IQ"]),
    ("965", ["KW"]),
    ("966", ["SA"]),
    ("967", ["YE"]),
    ("968", ["OM"]),
    ("970", ["PS"]),
    ("971", ["AE"]),
    ("972", ["IL"]),
    ("973", ["BH"]),
    ("974", ["QA"]),
    ("975", ["BT"]),
    ("976", ["MN"]),
    ("977", ["NP"]),
    ("992", ["TJ"]),
    ("993", ["TM"]),
    ("994", ["AZ"]),
    ("995", ["GE"]),
    ("996", ["KG"]),
    ("998", ["UZ"]),
  ]

  private static let callingCodeByRegion: [String: String] = Dictionary(
    lastWriteWins: callingCodeTable.flatMap { entry in entry.regions.map { ($0, entry.code) } })

  static func callingCode(forRegion region: String) -> String? {
    callingCodeByRegion[region.uppercased()]
  }
}
