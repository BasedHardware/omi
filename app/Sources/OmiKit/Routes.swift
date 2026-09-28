import Foundation

// Route vocabulary ported from `react-native/src/app/routes.ts` and the
// paired Route <-> MobileRoute maps in `AppOrchestrator.tsx`. Memories has no
// mobile surface of its own and lands on the mobile home route.

public enum Route: String, CaseIterable, Sendable, Hashable {
    case Home
    case Conversations
    case Memories
    case Tasks
    case Connectors
    case Settings

    public static func resolve(_ initialRoute: String?) -> Route {
        guard let initialRoute, let route = Route(rawValue: initialRoute) else {
            return .Home
        }
        return route
    }

    public var mobileRoute: MobileRoute {
        switch self {
        case .Home: return .home
        case .Conversations: return .chat
        case .Memories: return .home
        case .Tasks: return .tasks
        case .Settings: return .settings
        case .Connectors: return .apps
        }
    }
}

public enum MobileRoute: String, CaseIterable, Sendable, Hashable {
    case home
    case chat
    case tasks
    case settings
    case apps

    public var route: Route {
        switch self {
        case .home: return .Home
        case .chat: return .Conversations
        case .tasks: return .Tasks
        case .settings: return .Settings
        case .apps: return .Connectors
        }
    }
}
