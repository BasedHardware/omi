import Foundation

enum OmiComputerUseTool {

    static let openTag = "<computer_use>"
    static let closeTag = "</computer_use>"

    // The text to append to Claude's system prompt.
    static let systemPromptFragment: String = """

    ## Computer Use
    When the user asks you to perform an action on their computer — clicking a button, \
    typing text, opening an app, pressing a keyboard shortcut, scrolling — respond with \
    a VERY BRIEF (one short sentence, ≤ 12 words) plain-English preamble AND a computer \
    action plan on its own line at the end.

    Examples of good preambles:
      "On it — opening Notes."
      "Got it. Drafting that for you."
      "Sure, searching Spotify."

    DO NOT in the preamble:
      - Repeat or quote anything you are about to type (no email bodies, no note contents).
      - List or narrate the steps ("First I'll open Notes, then…"). The step list is \
        rendered separately from the `<computer_use>` block.
      - Add commentary, caveats, or context the user did not ask for.

    The action plan format:

    <computer_use>
    {"description":"<what you are doing>","steps":[
      {"action":"<type>","target":"<element label>","value":"<text>","step_description":"<brief label>"}
    ]}
    </computer_use>

    Action types: click, type, shortcut, scroll, open_app
    Value may include context variables: {{selection}} (selected text), {{clipboard}}, \
    {{transcript}} (what user just said), {{app}} (frontmost app name).

    ### CRITICAL: target labels for `click` steps
    The `target` is matched against real macOS Accessibility labels. To match, it MUST be:
      - The EXACT visible button/menu text only — nothing else.
      - Short (≤ 4 words). One or two words is best.
      - No descriptions, no positional words, no parentheticals, no icons.

    GOOD: "target":"New Note"          BAD: "target":"New Note button (pencil icon) in toolbar"
    GOOD: "target":"Send"              BAD: "target":"the blue Send button at the bottom"
    GOOD: "target":"File"              BAD: "target":"File menu in the menu bar"
    GOOD: "target":"Search"            BAD: "target":"search input field labeled What do you want to play?"

    If the visible label isn't obvious (e.g. an unlabeled icon), prefer a keyboard \
    shortcut over a guessed click. Examples: Cmd+N (new), Cmd+F (find), Cmd+L (URL/search), \
    Cmd+K (command palette), Cmd+, (settings).

    Emit multiple steps for compound commands ("add this to notes" = open Notes + Cmd+N + type).
    Emit one step for simple commands ("click Export").
    Only emit one <computer_use> block per response.
    If you cannot determine the target, ask the user to clarify instead of guessing.
    """

    /// Scans accumulated text for a complete <computer_use>...</computer_use> block.
    /// Returns (plan, textWithTagRemoved) if found, nil if no complete tag present.
    static func parse(from accumulatedText: String) -> (plan: OmiWorkflowPlan, cleanText: String)? {
        guard let openRange = accumulatedText.range(of: openTag),
              let closeRange = accumulatedText.range(of: closeTag),
              openRange.upperBound <= closeRange.lowerBound
        else { return nil }

        let jsonSubstring = accumulatedText[openRange.upperBound..<closeRange.lowerBound]
        let jsonString = jsonSubstring.trimmingCharacters(in: .whitespacesAndNewlines)

        guard let jsonData = jsonString.data(using: .utf8) else {
            log("OmiComputerUseTool: failed to encode JSON string as UTF-8")
            return nil
        }

        let decoder = JSONDecoder()

        do {
            let plan = try decoder.decode(OmiWorkflowPlan.self, from: jsonData)

            // Remove the entire tag block plus surrounding whitespace
            let fullTagRange = openRange.lowerBound..<closeRange.upperBound
            var cleanText = accumulatedText
            cleanText.replaceSubrange(fullTagRange, with: "")
            cleanText = cleanText.trimmingCharacters(in: .whitespacesAndNewlines)

            return (plan, cleanText)
        } catch {
            log("OmiComputerUseTool: failed to decode plan — \(error)")
            return nil
        }
    }
}
