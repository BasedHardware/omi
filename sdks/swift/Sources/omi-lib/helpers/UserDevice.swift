//
//  UserDevice.swift
//  PALApp
//
//  Created by Eric Bariaux on 02/07/2024.
//

import Foundation
import SwiftData


class UserDevice {    
    var name: String
    var deviceIdentifier: UUID
    var deviceType: UserDeviceType
    
    init(name: String, deviceIdentifier: UUID, deviceType: UserDeviceType) {
        self.name = name
        self.deviceIdentifier = deviceIdentifier
        self.deviceType = deviceType
    }
}

enum UserDeviceType: Codable, Hashable  {
    case wearable(WearableDevice.DeviceReference)
    case localMicrophone
    case appleWatch
}
