//
//  ContentView.swift
//  Omi Watch App
//
//  Created by Tomiwa Idowu on 3/20/25.
//

import SwiftUI

struct ContentView: View {
    @State private var isRecording: Bool = true
    
    var body: some View {
        NavigationStack {
            BackgroundStackView {
                
                GeometryReader { geometry in
                    let width = geometry.size.width
                    
                    VStack {
                        Spacer()
                        NavigationLink {
                            RecordingView()
                        } label: {
                            ZStack {
                                Circle()
                                    .fill(.gray.opacity(0.1))
                                    .strokeBorder(
                                        style: StrokeStyle(
                                            lineWidth: 0.5,
                                            dash: [2, 4]
                                        )
                                    )
                                    .scaleEffect(1)
                                
                                Image(.logo1)
                                    .resizable()
                                    .scaledToFit()
                                
                            }
                        }
                        .buttonStyle(.plain)
                        .frame(width: width * 0.5, height: width * 0.5)
                        
                        Spacer()
                        
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Image(.logo2)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 50, height: 50)
                }
                ToolbarItem(placement: .bottomBar) {
                    Text("Tap to Start")
                        .foregroundStyle(.white)
                        .font(.subheadline)
                }
            }
        }
    }
}

#Preview {
    ContentView()
}
