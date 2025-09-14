//
//  ContentView.swift
//  omiwatch Watch App
//
//  Created by Mohammed Mohsin on 13/09/25.
//

import SwiftUI

struct CounterView: View {
    @ObservedObject var viewModel: CounterViewModel
    var body: some View {
        VStack {
            Text("\(viewModel.count)")
                .font(.largeTitle)

            if viewModel.isRecording {
                Text("Recording...")
                    .foregroundColor(.red)
                    .font(.headline)
            }

            Spacer()

            HStack {
                Image(systemName: "minus.circle")
                    .imageScale(.large)
                    .foregroundStyle(.tint)
                    .font(.title)
                    .onTapGesture {
                        viewModel.decrement()
                    }
                Spacer()
                Image(systemName: "plus.circle")
                    .imageScale(.large)
                    .foregroundStyle(.tint)
                    .font(.title)
                    .onTapGesture {
                        viewModel.increment()
                    }
            }

            HStack {
                Button(action: {
                    if viewModel.isRecording {
                        viewModel.stopRecording()
                    } else {
                        viewModel.startRecording()
                    }
                }) {
                    Image(systemName: viewModel.isRecording ? "stop.circle.fill" : "mic.circle.fill")
                        .resizable()
                        .frame(width: 60, height: 60)
                        .foregroundColor(viewModel.isRecording ? .red : .blue)
                }
                .padding(.top, 10)
            }
        }
        .padding()
    }
}

#Preview {
    CounterView(viewModel: CounterViewModel())
}
