# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class OmiBleDiscoveryNamingTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)
  NAMING_SOURCE = File.join(IOS_ROOT, 'Runner', 'Ble', 'OmiBleDiscoveryNaming.swift')

  def test_names_devices_from_advertisement_or_fallback
    Dir.mktmpdir('omi-ble-discovery-naming') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'omi-ble-discovery-naming-test')
      File.write(harness, <<~SWIFT)
        import Foundation
        import CoreBluetooth

        @main
        struct OmiBleDiscoveryNamingTestHarness {
            static func check(_ condition: Bool, _ message: String) {
                precondition(condition, message)
            }

            static func advertisement(_ manufacturerData: Data?) -> [String: Any] {
                guard let manufacturerData else { return [:] }
                return [CBAdvertisementDataManufacturerDataKey: manufacturerData]
            }

            static func main() {
                // PLAUD manufacturer id 93 little-endian with the NotePin payload.
                let notePin = Data([0x5D, 0x00, 0x04, 0x56, 0xCF, 0x00])
                check(OmiBleDiscoveryNaming.isNotePinAdvertisement(advertisement(notePin)), "id + payload matches")
                check(!OmiBleDiscoveryNaming.isNotePinAdvertisement(
                    advertisement(Data([0x00, 0x5D, 0x04, 0x56, 0xCF, 0x00]))
                ), "big-endian id is rejected")
                check(!OmiBleDiscoveryNaming.isNotePinAdvertisement(
                    advertisement(Data([0x5D, 0x00, 0x04, 0x56, 0xCF]))
                ), "short payload is rejected")
                check(!OmiBleDiscoveryNaming.isNotePinAdvertisement(
                    advertisement(Data([0x5D, 0x00, 0x04, 0x56, 0xCF, 0x01]))
                ), "wrong payload is rejected")
                check(!OmiBleDiscoveryNaming.isNotePinAdvertisement(
                    advertisement(Data([0x00, 0x00, 0x04, 0x56, 0xCF, 0x00]))
                ), "other manufacturer is rejected")
                check(!OmiBleDiscoveryNaming.isNotePinAdvertisement([:]), "missing manufacturer data is rejected")

                // Precedence: advertised > cached > NotePin fallback > empty.
                check(OmiBleDiscoveryNaming.discoveredName(
                    advertisedLocalName: "NotePin S",
                    cachedName: "cached",
                    advertisementData: advertisement(notePin)
                ) == "NotePin S", "advertised name wins")
                check(OmiBleDiscoveryNaming.discoveredName(
                    advertisedLocalName: "  NotePin S  ",
                    cachedName: nil,
                    advertisementData: [:]
                ) == "NotePin S", "advertised name is trimmed")
                check(OmiBleDiscoveryNaming.discoveredName(
                    advertisedLocalName: "   ",
                    cachedName: "cached",
                    advertisementData: [:]
                ) == "cached", "blank advertised name falls back to cached")
                check(OmiBleDiscoveryNaming.discoveredName(
                    advertisedLocalName: nil,
                    cachedName: "cached",
                    advertisementData: [:]
                ) == "cached", "cached name is used when nothing is advertised")
                check(OmiBleDiscoveryNaming.discoveredName(
                    advertisedLocalName: nil,
                    cachedName: nil,
                    advertisementData: advertisement(notePin)
                ) == "NotePin", "NotePin fallback fills the empty name")
                check(OmiBleDiscoveryNaming.discoveredName(
                    advertisedLocalName: "",
                    cachedName: "  ",
                    advertisementData: advertisement(notePin)
                ) == "NotePin", "blank names fall through to the NotePin fallback")
                check(OmiBleDiscoveryNaming.discoveredName(
                    advertisedLocalName: nil,
                    cachedName: nil,
                    advertisementData: [:]
                ) == "", "unnamed non-NotePin peripheral stays empty")
            }
        }
      SWIFT

      stdout, stderr, compile_status = Open3.capture3(
        'swiftc',
        '-parse-as-library',
        NAMING_SOURCE,
        harness,
        '-o',
        binary
      )
      assert compile_status.success?, "compile failed: #{stderr}\n#{stdout}"

      stdout, stderr, run_status = Open3.capture3(binary)
      assert run_status.success?, "run failed: #{stderr}\n#{stdout}"
    end
  end
end
