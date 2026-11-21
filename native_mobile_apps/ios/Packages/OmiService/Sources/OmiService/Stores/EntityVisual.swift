import Foundation
import OmiCore

/// What a task or conversation shows as its picture. Only hard signals name a brand (a wrong logo
/// is worse than a neutral one): a known service named in the text, or a company address among
/// the people. Otherwise the person the task is about, then the conversation's emoji, then a
/// category glyph.
public enum EntityVisual: Equatable, Sendable {
    /// A brand: `bundled` is a logo the app ships (`OmiMedia.logo`), else load it by `domain`.
    case brand(domain: String, bundled: String? = nil)
    case person(name: String, email: String?)
    case emoji(String, category: String?)
    case symbol(String)

    public static func forTask(_ task: ActionItem, source: Conversation?) -> EntityVisual {
        brandNamed(in: task.description) ?? companyAmong(source)
            ?? personIn(task.description, conversation: source) ?? quiet(source)
    }

    public static func forConversation(_ conversation: Conversation) -> EntityVisual {
        brandNamed(in: conversation.title) ?? companyAmong(conversation) ?? quiet(conversation)
    }

    /// No brand, no person: the conversation's emoji, else its category glyph. Also what a logo
    /// that fails to load falls back to.
    public static func quiet(_ conversation: Conversation?) -> EntityVisual {
        conversation?.emoji.map { .emoji($0, category: conversation?.category) }
            ?? .symbol(categorySymbol(conversation?.category))
    }

    /// A service named as a word in `text` ("Email the deck via Gmail", "Notion page").
    public static func brandNamed(in text: String) -> EntityVisual? {
        let lower = text.lowercased()
        let words = Set(lower.split { !($0.isLetter || $0.isNumber || $0 == ".") }.map(String.init))
        return services.first { name, _ in name.contains(" ") ? lower.contains(name) : words.contains(name) }?.brand
    }

    /// The first company address (not a freemail or placeholder domain) among the people.
    public static func companyAmong(_ conversation: Conversation?) -> EntityVisual? {
        for person in conversation?.people ?? [] {
            guard let email = person.email, let at = email.lastIndex(of: "@") else { continue }
            let domain = registrable(String(email[email.index(after: at)...]).lowercased())
            if isCompany(domain) { return .brand(domain: domain) }
        }
        return nil
    }

    /// Someone from the conversation whose first name the task mentions ("Send Anna the deck").
    public static func personIn(_ text: String, conversation: Conversation?) -> EntityVisual? {
        let words = Set(text.lowercased().split { !($0.isLetter || $0.isNumber || $0 == "_") }.map(String.init))
        for person in conversation?.people ?? [] {
            let name = person.name ?? person.email?.split(separator: "@").first.map { $0.prefix(1).uppercased() + $0.dropFirst() }
            guard let name, let first = name.split(separator: " ").first?.lowercased(), first.count > 1 else { continue }
            if words.contains(first) { return .person(name: name, email: person.email) }
        }
        return nil
    }

    public static func categorySymbol(_ category: String?) -> String {
        switch category {
        case "health": "heart"
        case "finance", "economics": "creditcard"
        case "travel": "airplane"
        case "work", "business": "briefcase"
        case "education": "graduationcap"
        case "family", "personal": "person"
        case "social": "person.2"
        case "technology": "laptopcomputer"
        default: "checklist"
        }
    }

    private static func registrable(_ host: String) -> String {
        let host = host.hasPrefix("www.") ? String(host.dropFirst(4)) : host
        return host.split(separator: ".").suffix(2).joined(separator: ".")
    }

    private static func isCompany(_ domain: String) -> Bool {
        guard domain.contains("."), !freemail.contains(domain) else { return false }
        return !["test", "local", "invalid", "example"].contains(domain.split(separator: ".").last.map(String.init) ?? "")
    }

    private static let freemail: Set<String> = [
        "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "yahoo.com", "icloud.com",
        "me.com", "mac.com", "aol.com", "proton.me", "protonmail.com", "gmx.de", "gmx.net", "web.de", "t-online.de",
        "mail.com", "yandex.com", "example.com", "example.org", "example.net",
    ]

    /// Services worth a logo when a task names them; bundled marks where the app ships one.
    private static let services: [(name: String, brand: EntityVisual)] = [
        ("gmail", .brand(domain: "gmail.com", bundled: "gmail")),
        ("google calendar", .brand(domain: "calendar.google.com", bundled: "google_calendar")),
        ("todoist", .brand(domain: "todoist.com", bundled: "todoist")),
        ("asana", .brand(domain: "asana.com", bundled: "asana")),
        ("clickup", .brand(domain: "clickup.com", bundled: "clickup")),
        ("google tasks", .brand(domain: "tasks.google.com", bundled: "google_tasks")),
        ("slack", .brand(domain: "slack.com")),
        ("notion", .brand(domain: "notion.so")),
        ("linear", .brand(domain: "linear.app")),
        ("github", .brand(domain: "github.com")),
        ("figma", .brand(domain: "figma.com")),
        ("zoom", .brand(domain: "zoom.us")),
        ("whatsapp", .brand(domain: "whatsapp.com")),
        ("linkedin", .brand(domain: "linkedin.com")),
        ("stripe", .brand(domain: "stripe.com")),
        ("uber", .brand(domain: "uber.com")),
        ("airbnb", .brand(domain: "airbnb.com")),
        ("amazon", .brand(domain: "amazon.com")),
        ("spotify", .brand(domain: "spotify.com")),
        ("dropbox", .brand(domain: "dropbox.com")),
        ("jira", .brand(domain: "atlassian.com")),
        ("hubspot", .brand(domain: "hubspot.com")),
        ("salesforce", .brand(domain: "salesforce.com")),
    ]
}
