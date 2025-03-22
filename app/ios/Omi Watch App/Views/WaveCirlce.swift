//
//  WaveCirlce.swift
//  OmiWatchApp Watch App
//
//  Created by Tomiwa Idowu on 3/18/25.
//

import SwiftUI

struct WaveCirlce: View {
    @State private var animating: Bool = false
    var body: some View {
        Circle()
            .strokeBorder(.white, lineWidth: 1)
            .foregroundStyle(.white)
            .scaleEffect(animating ? 1 : 0)
            .opacity(animating ? 0 : 1)
            .animation(
                .linear(duration: 1)
                .repeatForever(autoreverses: false),
                value: animating
            )
            .onAppear {
                animating.toggle()
            }
    }
}

#Preview {
    WaveCirlce()
}
