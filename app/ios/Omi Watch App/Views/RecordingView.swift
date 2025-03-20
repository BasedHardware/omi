//
//  RecordingView.swift
//  OmiWatchApp Watch App
//
//  Created by Tomiwa Idowu on 3/18/25.
//

import SwiftUI

struct RecordingView: View {
    @State private var isRecording: Bool = true
    @State private var animating: Bool = true
    @GestureState private var isDetectingLongPress = false
    @State private var completedLongPress = false
    
    var longPress: some Gesture {
        LongPressGesture(minimumDuration: 5)
            .updating($isDetectingLongPress) { currentState, gestureState,
                transaction in
                gestureState = currentState
//                transaction.animation = Animation.easeIn(duration: 2.0)
            }
            .onEnded { finished in
                self.completedLongPress = finished
                print("end")
            }
    }
    
    var body: some View {
        NavigationStack {
            BackgroundStackView {
                GeometryReader { geometry in
                    let width = geometry.size.width
                    let height = geometry.size.height
                    let centerCircleWidth = width * 0.8;
                    
                    ZStack {
                        ForEach(1..<5, id: \.self) { index in
                            WaveCirlce()
                                .frame(width: CGFloat(index) * (centerCircleWidth * 0.5), height: CGFloat(index) * (centerCircleWidth * 0.5))
                            
                        }
                        
                        ZStack {
                            Circle()
                                .fill(self.isDetectingLongPress ? .white.opacity(0.8) : .white
                                )
                                .frame(width: centerCircleWidth, height: centerCircleWidth)
                                .shadow(color: .gray.opacity(0.5), radius: 10, x: 7, y: 7)
                            Image(systemName: "waveform")
                                .foregroundColor(.black)
                                .font(.system(size: 50, weight: .semibold))
                                .symbolEffect(
                                    .variableColor.iterative,
                                    isActive: self.isDetectingLongPress
                                )
                            GeometryReader { geometry in
                                ArcText(text: "Tap & Hold to speak", arcDegrees: -180, size: geometry.size)
                            }
                            .offset(x: 0, y: (centerCircleWidth * 0.4))
                        }
                        .scaleEffect(self.isDetectingLongPress ? 0.95 : 1)
                        .gesture(longPress)
                        .onChange(of: self.isDetectingLongPress) { oldValue, newValue in
                            if(newValue) {
//                                RecordManager.shared.startRecording();
                            } else {
//                                RecordManager.shared.stopRecording();
                            }
                        }
                    }
                    .position(x: width / 2, y: height / 2)
                }
                
            }
            .toolbar {
                ToolbarItem(placement: .bottomBar) {
                    HStack(alignment: .bottom) {
                        Button {
                            print("stop")
                        } label: {
                            Image(systemName: "stop.fill")
                        }
                        Spacer()
                        Button {
                            print("mic")
                        } label: {
                            Image(systemName: "microphone.slash.fill")
                        }
                    }
                }
            }
        }
    }
}

#Preview {
    RecordingView()
}
