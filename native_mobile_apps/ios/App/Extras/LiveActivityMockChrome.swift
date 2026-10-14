#if DEBUG
    import SwiftUI

    /// Stand-ins for the system's chrome around a Live Activity, for `LiveActivityRenderer`: the Lock
    /// Screen card and the Dynamic Island's expanded, compact and minimal shapes at an iPhone 17
    /// Pro's (402 pt) measurements. The regions inside are the real views.
    enum LiveActivityMockChrome {
        static let lockWidth: CGFloat = 374
        static let islandWidth: CGFloat = 378
        static let islandHeight: CGFloat = 160
        static let margin: CGFloat = 12
        static let camera: CGFloat = 132
        /// Where the expanded bottom region starts.
        static let bottomTop: CGFloat = 78

        /// A wallpaper behind the translucent card.
        static func backdrop(_ content: some View) -> some View {
            content
                .padding(14)
                .background(LinearGradient(colors: [Color(red: 0.24, green: 0.30, blue: 0.42), Color(red: 0.10, green: 0.12, blue: 0.18)],
                                           startPoint: .topLeading, endPoint: .bottomTrailing))
        }

        static func lockScreen(card: some View, tint: Color) -> some View {
            backdrop(card
                .frame(width: lockWidth)
                .background(tint, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
                .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                .environment(\.colorScheme, .dark))
        }

        static func expanded(leading: some View, trailing: some View, bottom: some View) -> some View {
            let side = (islandWidth - 2 * margin - camera) / 2
            return backdrop(ZStack(alignment: .top) {
                RoundedRectangle(cornerRadius: 46, style: .continuous).fill(.black)
                VStack(spacing: 0) {
                    HStack(spacing: 0) {
                        leading.frame(width: side)
                        Color.clear.frame(width: camera)
                        trailing.frame(width: side)
                    }
                    .frame(height: bottomTop - 8)
                    .padding(.top, 8)
                    bottom.frame(height: islandHeight - bottomTop - 12)
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, margin)
                // The camera, to see what sits beside it.
                Capsule().fill(Color(white: 0.11)).frame(width: 126, height: 37).padding(.top, 11)
            }
            .frame(width: islandWidth, height: islandHeight)
            .environment(\.colorScheme, .dark))
        }

        static func compact(leading: some View, trailing: some View) -> some View {
            backdrop(HStack(spacing: 0) {
                leading.padding(.leading, 10)
                Color.clear.frame(width: 126)
                trailing.padding(.trailing, 10)
            }
            .frame(height: 37)
            .background(.black, in: Capsule())
            .environment(\.colorScheme, .dark))
        }

        static func minimal(_ content: some View) -> some View {
            backdrop(content
                .frame(width: 37, height: 37)
                .background(.black, in: Circle())
                .environment(\.colorScheme, .dark))
        }
    }
#endif
