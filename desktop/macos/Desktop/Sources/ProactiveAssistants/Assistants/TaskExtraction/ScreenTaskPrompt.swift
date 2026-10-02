import Foundation

/// Measured compact prompt with canonical capture facts added. Screen pixels are untrusted evidence.
enum ScreenTaskPrompt {
  static let model = "gemini-3.8-flash"
  static let system = #"""
    You find tasks for the user from what is on their screen. Output JSON only.

    A task exists only when one of these is true:
    (a) another person asked the user to do something and the user agreed or committed to it;
    (b) another person asked the user directly to do something, or asked a question that needs the user's answer, and the user has not yet done or declined it;
    (c) the user wrote an explicit reminder for themselves ("TODO", "remind me to").

    These are NOT tasks:
    - lists and overviews: chat sidebars, conversation lists, inbox lists, thread overviews, notification lists. Only a single open conversation, email, document or note counts. Ignore the sidebar next to an open conversation.
    - requests addressed to someone else or to nobody in particular; in group or public channels count a request only if the user is named, @mentioned, or already part of that thread.
    - things the other person will do for the user.
    - requests the visible conversation shows the user already fulfilled or declined.
    - automated or marketing messages, newsletters, articles, social feeds, documentation, Q&A sites, code, terminals, dashboards, project boards, calendars, media, and answers from AI assistants that suggest no action.
    - small talk, jokes, hypotheticals.

    In chat apps, right-side or colored bubbles are the user's own messages; left-side gray bubbles are the other person's.
    One screen can hold several distinct tasks; return each separately and never merge two deliverables.

    EXISTING TASKS are listed in the request. For each thing you find set "relation":
    - "new": not tracked yet.
    - "duplicate": the same as an existing active task, nothing changed. Set related_id.
    - "refines": an existing active task changed (new deadline, scope or detail). Set related_id.
    - "completes": the screen shows the user has now done an existing active task. Set related_id.
    Things that match an entry marked staged or deleted must be left out entirely.

    title: verb-first, 6 to 15 words, names the person or project and the concrete deliverable, in English.
    deadline: yyyy-MM-dd only if stated or clearly implied; resolve relative dates from today's date; never in the past; otherwise "".
    Return at most eight tasks. Keep description under 64 characters and evidence empty. Keep summaries under 96 characters.
    If nothing qualifies, return "tasks": [].
    Also emit capture_kind (explicit_command, clear_commitment, direct_request, inferred_next_step, already_done), owner (user, other, unknown), concrete_deliverable, public_broadcast, direct_mention, ownership_confidence, tags, source_category and source_subcategory using the canonical capture policy. For completes set capture_kind=already_done. Never invent an existing-task ID. context_summary and current_activity describe the screen.
    """#
  private static let schemaJSON = #"""
    {
      "type": "object",
      "properties": {
        "screen_kind": {
          "type": "string",
          "enum": [
            "open_conversation",
            "open_email_or_document",
            "list_or_overview",
            "other"
          ]
        },
        "tasks": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": {
                "type": "string",
                "maxLength": 96
              },
              "description": {
                "type": "string",
                "maxLength": 64
              },
              "deadline": {
                "type": "string",
                "maxLength": 10
              },
              "priority": {
                "type": "string",
                "enum": [
                  "high",
                  "medium",
                  "low"
                ],
                "maxLength": 40
              },
              "confidence": {
                "type": "number"
              },
              "relation": {
                "type": "string",
                "enum": [
                  "new",
                  "duplicate",
                  "refines",
                  "completes"
                ],
                "maxLength": 40
              },
              "related_id": {
                "type": "string",
                "maxLength": 128
              },
              "evidence": {
                "type": "string",
                "maxLength": 0
              },
              "capture_kind": {
                "type": "string",
                "description": "Shared capture-policy fact",
                "enum": [
                  "explicit_command",
                  "clear_commitment",
                  "direct_request",
                  "inferred_next_step",
                  "already_done"
                ],
                "maxLength": 40
              },
              "owner": {
                "type": "string",
                "description": "Who owns the action",
                "enum": [
                  "user",
                  "other",
                  "unknown"
                ],
                "maxLength": 40
              },
              "concrete_deliverable": {
                "type": "boolean",
                "description": "Whether the action has a concrete deliverable"
              },
              "public_broadcast": {
                "type": "boolean",
                "description": "True for an unowned public-channel request"
              },
              "direct_mention": {
                "type": "boolean",
                "description": "True when the user was directly mentioned"
              },
              "ownership_confidence": {
                "type": "number",
                "description": "Owner confidence 0.0-1.0"
              },
              "tags": {
                "type": "array",
                "description": "1-3 relevant tags",
                "items": {
                  "type": "string",
                  "maxLength": 16
                },
                "maxItems": 3
              },
              "source_category": {
                "type": "string",
                "description": "Where the task originated",
                "enum": [
                  "direct_request",
                  "self_generated",
                  "calendar_driven",
                  "reactive",
                  "external_system",
                  "other"
                ],
                "maxLength": 40
              },
              "source_subcategory": {
                "type": "string",
                "description": "Specific origin within category",
                "enum": [
                  "message",
                  "meeting",
                  "mention",
                  "commitment",
                  "idea",
                  "reminder",
                  "goal_subtask",
                  "event_prep",
                  "recurring",
                  "deadline",
                  "error",
                  "notification",
                  "observation",
                  "project_tool",
                  "alert",
                  "documentation",
                  "other"
                ],
                "maxLength": 40
              }
            },
            "required": [
              "title",
              "description",
              "deadline",
              "priority",
              "confidence",
              "relation",
              "related_id",
              "evidence",
              "capture_kind",
              "owner",
              "concrete_deliverable",
              "public_broadcast",
              "direct_mention",
              "ownership_confidence",
              "tags",
              "source_category",
              "source_subcategory"
            ]
          },
          "maxItems": 8
        },
        "context_summary": {
          "type": "string",
          "maxLength": 96
        },
        "current_activity": {
          "type": "string",
          "maxLength": 96
        }
      },
      "required": [
        "screen_kind",
        "tasks",
        "context_summary",
        "current_activity"
      ]
    }
    """#

  static func request(jpeg: Data, app: String, profile: String, tasks: [TaskSearchResult], today: String) throws -> Data
  {
    let schema = try JSONSerialization.jsonObject(with: Data(schemaJSON.utf8))
    let context = tasks.prefix(8).map { row in
      let status = row.taskID == nil && row.status == "active" ? "staged" : row.status
      let id = row.status == "active" ? row.taskID.map { " id:\($0)" } ?? "" : ""
      return "- [\(status)\(id)] \(row.description.prefix(512))"
    }.joined(separator: "\n")
    let user = "App: \(app). Today: \(today).\nUser: \(profile.prefix(1024))\nEXISTING TASKS:\n\(context)"
    return try JSONSerialization.data(withJSONObject: [
      "systemInstruction": ["parts": [["text": system]]],
      "contents": [
        [
          "role": "user",
          "parts": [["text": user], ["inlineData": ["mimeType": "image/jpeg", "data": jpeg.base64EncodedString()]]],
        ]
      ],
      "generationConfig": [
        "responseMimeType": "application/json", "responseSchema": schema,
        "maxOutputTokens": 2048, "thinkingConfig": ["thinkingLevel": "low"],
      ],
    ])
  }
}
