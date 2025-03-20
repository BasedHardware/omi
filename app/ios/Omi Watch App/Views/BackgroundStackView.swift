//
//  BackgroundView.swift
//  OmiWatchApp Watch App
//
//  Created by Tomiwa Idowu on 3/18/25.
//

import SwiftUI

struct BackgroundStackView<Content: View>: View {
    @ViewBuilder var content: () -> Content
    var body: some View {
        ZStack {
            Image(.background)
                .resizable()
                .scaledToFill()
                .ignoresSafeArea()
            content()
        }
    }
}
