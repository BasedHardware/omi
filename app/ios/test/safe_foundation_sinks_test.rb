# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class SafeFoundationSinksTest < Minitest::Test
  SOURCE = File.expand_path('../Runner/SafeFoundationSinks.swift', __dir__)

  def test_hostile_native_sink_inputs
    Dir.mktmpdir('omi-safe-foundation') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'safe-foundation-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        struct CustomValue { let number: Int }
        struct Record: Codable, Equatable { let level: Double }

        let suite = "omi-safe-sinks-\\(UUID().uuidString)"
        guard let defaults = UserDefaults(suiteName: suite) else { fatalError("missing suite") }
        defer { defaults.removePersistentDomain(forName: suite) }

        // A nil update removes the key; no Optional is ever bridged as Any.
        try SafeDefaults.set(.int(7), forKey: "scalar", in: defaults)
        precondition(defaults.integer(forKey: "scalar") == 7)
        try SafeDefaults.store(.string("checked"), forKey: "stored", in: defaults)
        precondition(defaults.string(forKey: "stored") == "checked")
        try SafeDefaults.set(nil, forKey: "scalar", in: defaults)
        precondition(defaults.object(forKey: "scalar") == nil)
        try SafeDefaults.set(.dictionary(["date": .date(Date(timeIntervalSince1970: 0))]),
                             forKey: "plist", in: defaults)
        precondition(defaults.dictionary(forKey: "plist")?["date"] is Date)
        precondition((try? SafeDefaults.set(.array([.double(.nan)]), forKey: "bad", in: defaults)) == nil)
        precondition(defaults.object(forKey: "bad") == nil)
        try SafeDefaults.setPlistRecords([["ts": .int64(123), "level": .int(80)]],
                                         forKey: "history", in: defaults)
        precondition((defaults.array(forKey: "history") as? [[String: Int]])?.first?["level"] == 80)
        precondition((try? SafeDefaults.setPlistRecords([["bad": .double(.infinity)]],
                                                       forKey: "bad-history", in: defaults)) == nil)
        precondition(defaults.object(forKey: "bad-history") == nil)

        try SafeDefaults.setRecords([Record(level: 42)], forKey: "records", in: defaults)
        let restored = try SafeDefaults.records(Record.self, forKey: "records", in: defaults)
        precondition(restored == [Record(level: 42)])
        precondition((try? SafeDefaults.setRecords([Record(level: .infinity)], forKey: "bad-records", in: defaults)) == nil)
        precondition(defaults.object(forKey: "bad-records") == nil)
        try SafeDefaults.setRecords(Optional<[Record]>.none, forKey: "records", in: defaults)
        precondition(defaults.object(forKey: "records") == nil)

        let json = try SafeJSON.data(withJSONObject: ["value": 1, "null": NSNull()])
        let decoded = try JSONSerialization.jsonObject(with: json)
        precondition(JSONSerialization.isValidJSONObject(decoded))
        for bad: Any in [Double.nan, Double.infinity, Date(), CustomValue(number: 1)] {
            precondition((try? SafeJSON.data(withJSONObject: ["bad": bad])) == nil)
        }
        precondition((try? SafeJSON.data(withJSONObject: ["bad": [Double.nan]])) == nil)
        precondition((try? SafeJSON.data(withJSONObject: ["bad": Data([1])])) == nil)

        precondition(CheckedIntegerConversion.int64(12.9) == 12)
        precondition(CheckedIntegerConversion.int64(-12.9) == -12)
        precondition(CheckedIntegerConversion.int64(.nan) == nil)
        precondition(CheckedIntegerConversion.int64(.infinity) == nil)
        precondition(CheckedIntegerConversion.int64(Double(Int64.max)) == nil)
        precondition(CheckedIntegerConversion.int(Double.infinity) == nil)
        precondition(CheckedIntegerConversion.epochMs(Date(timeIntervalSince1970: 1.2349)) == 1234)
        let beforeDefaultEpoch = Date()
        let defaultEpochMs = CheckedIntegerConversion.epochMs()
        let afterDefaultEpoch = Date()
        precondition((CheckedIntegerConversion.epochMs(beforeDefaultEpoch)...CheckedIntegerConversion.epochMs(afterDefaultEpoch)).contains(defaultEpochMs))
      SWIFT
      stdout, stderr, compile = Open3.capture3('swiftc', SOURCE, harness, '-o', binary)
      assert compile.success?, "swiftc failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, run = Open3.capture3(binary)
      assert run.success?, "sink assertions failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_arbitrary_model_cannot_reach_plist_api
    Dir.mktmpdir('omi-safe-foundation-typecheck') do |directory|
      harness = File.join(directory, 'main.swift')
      File.write(harness, <<~SWIFT)
        import Foundation
        struct CustomValue { let number: Int }
        try SafeDefaults.set(CustomValue(number: 1), forKey: "bad")
      SWIFT
      _stdout, stderr, compile = Open3.capture3('swiftc', '-typecheck', SOURCE, harness)
      refute compile.success?, 'arbitrary model unexpectedly passed the typed persistence boundary'
      assert_match(/cannot convert value of type 'CustomValue'/, stderr)
    end
  end
end
