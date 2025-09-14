//
//  omiwatchApp.swift
//  omiwatch Watch App
//
//  Created by Mohammed Mohsin on 13/09/25.
//

import SwiftUI

@main
struct omiwatch_Watch_AppApp: App {
    var body: some Scene {
        WindowGroup {
            CounterView(viewModel: CounterViewModel())
        }
    }
}
