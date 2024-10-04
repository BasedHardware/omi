//
//  BLEAssignedNumber.swift
//  PALApp
//
//  Created by Eric Bariaux on 23/05/2024.
//

import Foundation
import CoreBluetooth

enum BatteryService {
    public static let serviceUUID = CBUUID(string: "0x180F")
    public static let batteryLevelCharacteristicUUID = CBUUID(string: "0x2A19")
    public static let batteryLevelStatusCharacteristicUUID = CBUUID(string: "0x2BED")
}
