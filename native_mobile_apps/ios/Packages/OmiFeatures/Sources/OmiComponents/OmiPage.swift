import OmiDesign
import SwiftUI

public extension View {
    /// A pushed settings-style page as Omi shows it: small centered title on the black page,
    /// grouped rows on cards.
    func omiPage(_ title: String) -> some View {
        scrollContentBackground(.hidden)
            .background(DS.Palette.background)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
    }
}
