//
//  ArcText.swift
//  OmiWatchApp Watch App
//
//  Created by Tomiwa Idowu on 3/19/25.
//

import SwiftUI

struct ArcText: View {
    let text: String
    let arcDegrees: Double
    let size: CGSize
    
    var body: some View {
        let letters = Array(text)
        let letterCount = letters.count
        let chordLength = size.width * 0.4 // The effective width of the arc text
        let centerY = size.height / 2
        let totalArcRad = arcDegrees * .pi / 180 // Convert degrees to radians
        
        // Calculate the radius of the circle forming the arc
        let safeArcRad = max(abs(totalArcRad), 0.0001) // Prevent division by zero
        let radius = chordLength / (2 * CGFloat(sin(safeArcRad / 2)))
        
        // Determine the circle's center
        let circleCenter = CGPoint(x: size.width / 2, y: centerY + (arcDegrees > 0 ? radius : -radius))
        
        return ZStack {
            ForEach(0..<letterCount, id: \.self) { index in
                let letterAngle = -totalArcRad / 2 + totalArcRad * Double(index) / Double(letterCount - 1)
                
                // Compute the position of the letter on the arc
                let position = CGPoint(
                    x: circleCenter.x + radius * CGFloat(sin(letterAngle)),
                    y: circleCenter.y - radius * CGFloat(cos(letterAngle))
                )
                
                Text(String(letters[index]))
                    .font(.headline)
                    .foregroundColor(.black)
                    .position(position)
                    .rotationEffect(.degrees(-angleInDegrees(letterAngle))) // Rotate upright
            }
        }
    }
    
    func angleInDegrees(_ radians: Double) -> Double {
        return radians * 180 / .pi
    }
}
