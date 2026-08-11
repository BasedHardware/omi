import type { MessageKey } from "@omi-core/i18n";

export type ProductionRoute =
  | "home"
  | "memories"
  | "conversations"
  | "folders"
  | "tasks"
  | "chat"
  | "settings"
  | "listen";

export type ProductionCommandId =
  | "open-command-palette"
  | "navigate-home"
  | "navigate-memories"
  | "navigate-conversations"
  | "navigate-folders"
  | "navigate-tasks"
  | "navigate-chat"
  | "navigate-settings"
  | "navigate-listen"
  | "focus-home-search"
  | "new-task"
  | "navigate-task"
  | "delete-task"
  | "indent-task"
  | "outdent-task"
  | "save-memory"
  | "cancel-memory"
  | "send-chat"
  | "close-command-palette";

export type TextEntryPolicy = "ignore" | "allow" | "text-only";
export type CommandRepeatPolicy = "allow" | "ignore";

export type CommandChord = {
  readonly key: string;
  /** A modifier chord accepts either Meta (macOS/iOS hardware keyboard) or Control. */
  readonly modifier?: boolean;
  readonly shift?: boolean;
  readonly alt?: boolean;
};

export type ProductionCommandContext = {
  readonly activeRoute: ProductionRoute;
  readonly navigate: (route: ProductionRoute) => void;
  readonly handlers?: Partial<Record<ProductionCommandId, (event?: KeyboardEvent) => void | Promise<void>>>;
  readonly enabled?: Partial<Record<ProductionCommandId, boolean>>;
  readonly paletteOpen?: boolean;
};

export type ProductionCommand = {
  readonly id: ProductionCommandId;
  readonly labelKey: MessageKey;
  readonly descriptionKey?: MessageKey;
  readonly chord?: CommandChord;
  readonly chords?: readonly CommandChord[];
  readonly routeScope: ProductionRoute | "global";
  readonly textEntryPolicy: TextEntryPolicy;
  readonly repeatPolicy: CommandRepeatPolicy;
  readonly isEnabled: (context: ProductionCommandContext) => boolean;
  readonly invoke: (context: ProductionCommandContext, event?: KeyboardEvent) => void | Promise<void>;
};

const routeCommand = (
  id: ProductionCommandId,
  labelKey: MessageKey,
  route: ProductionRoute,
): ProductionCommand => ({
  id,
  labelKey,
  routeScope: "global",
  textEntryPolicy: "ignore",
  repeatPolicy: "allow",
  isEnabled: () => true,
  invoke: (context) => context.navigate(route),
});

const handlerCommand = (
  definition: Omit<ProductionCommand, "isEnabled" | "invoke">,
): ProductionCommand => ({
  ...definition,
  isEnabled: (context) => context.enabled?.[definition.id] ?? Boolean(context.handlers?.[definition.id]),
  invoke: (context, event) => {
    const handler = context.handlers?.[definition.id];
    if (handler) return handler(event);
  },
});

/**
 * The sole command inventory for production surfaces. IDs are stable across
 * platforms; labels and chords are projections of this list for web/native hosts.
 */
export function createProductionCommandRegistry(): readonly ProductionCommand[] {
  return [
    handlerCommand({
      id: "open-command-palette",
      labelKey: "tasks.shortcuts",
      descriptionKey: "shortcuts.openSearch",
      chord: { key: "p", modifier: true, shift: true },
      routeScope: "global",
      textEntryPolicy: "ignore",
      repeatPolicy: "ignore",
    }),
    routeCommand("navigate-home", "nav.home", "home"),
    routeCommand("navigate-memories", "nav.memories", "memories"),
    routeCommand("navigate-conversations", "nav.conversations", "conversations"),
    routeCommand("navigate-folders", "nav.folders", "folders"),
    routeCommand("navigate-tasks", "nav.tasks", "tasks"),
    routeCommand("navigate-chat", "chat.title", "chat"),
    routeCommand("navigate-settings", "nav.settings", "settings"),
    routeCommand("navigate-listen", "listen.title", "listen"),
    handlerCommand({
      id: "focus-home-search",
      labelKey: "shortcuts.openSearch",
      chord: { key: "k", modifier: true },
      routeScope: "home",
      textEntryPolicy: "allow",
      repeatPolicy: "allow",
    }),
    handlerCommand({
      id: "new-task",
      labelKey: "tasks.newTask",
      chord: { key: "n", modifier: true },
      routeScope: "tasks",
      textEntryPolicy: "ignore",
      repeatPolicy: "ignore",
    }),
    handlerCommand({
      id: "navigate-task",
      labelKey: "tasks.shortcutNavigate",
      chords: [{ key: "ArrowDown" }, { key: "ArrowUp" }],
      routeScope: "tasks",
      textEntryPolicy: "ignore",
      repeatPolicy: "allow",
    }),
    handlerCommand({
      id: "delete-task",
      labelKey: "tasks.shortcutDelete",
      chord: { key: "d", modifier: true },
      routeScope: "tasks",
      textEntryPolicy: "ignore",
      repeatPolicy: "ignore",
    }),
    handlerCommand({
      id: "indent-task",
      labelKey: "tasks.shortcutIndent",
      chord: { key: "]", modifier: true },
      routeScope: "tasks",
      textEntryPolicy: "ignore",
      repeatPolicy: "ignore",
    }),
    handlerCommand({
      id: "outdent-task",
      labelKey: "tasks.shortcutOutdent",
      chord: { key: "[", modifier: true },
      routeScope: "tasks",
      textEntryPolicy: "ignore",
      repeatPolicy: "ignore",
    }),
    handlerCommand({
      id: "save-memory",
      labelKey: "common.save",
      chord: { key: "Enter", modifier: true },
      routeScope: "memories",
      textEntryPolicy: "allow",
      repeatPolicy: "ignore",
    }),
    handlerCommand({
      id: "cancel-memory",
      labelKey: "common.cancel",
      chord: { key: "Escape" },
      routeScope: "memories",
      textEntryPolicy: "allow",
      repeatPolicy: "ignore",
    }),
    handlerCommand({
      id: "send-chat",
      labelKey: "chat.send",
      chord: { key: "Enter" },
      routeScope: "chat",
      textEntryPolicy: "text-only",
      repeatPolicy: "ignore",
    }),
    handlerCommand({
      id: "close-command-palette",
      labelKey: "common.close",
      chord: { key: "Escape" },
      routeScope: "global",
      textEntryPolicy: "allow",
      repeatPolicy: "ignore",
    }),
  ];
}

function normalizedKey(key: string): string {
  return key.length === 1 ? key.toLocaleLowerCase() : key;
}

export function isTextEntryTarget(target: EventTarget | null): boolean {
  return typeof HTMLElement !== "undefined" && target instanceof HTMLElement && Boolean(target.closest("input, textarea, select, [contenteditable='true']"));
}

export function chordMatches(event: KeyboardEvent, chord: CommandChord): boolean {
  if (normalizedKey(event.key) !== normalizedKey(chord.key)) return false;
  // Omitted modifiers mean "plain key". `modifier: true` deliberately aliases
  // Meta and Control for desktop/macOS and hardware-keyboard iOS; it never
  // permits a chord with an additional modifier to leak into a text field.
  const platformModifierCount = Number(event.metaKey) + Number(event.ctrlKey);
  if (chord.modifier === true ? platformModifierCount !== 1 : platformModifierCount !== 0) return false;
  if (event.shiftKey !== (chord.shift ?? false)) return false;
  if (event.altKey !== (chord.alt ?? false)) return false;
  return true;
}

/**
 * IME composition can surface Enter/Escape as ordinary keydowns on browsers
 * that do not consistently set `isComposing`; keyCode 229 is their settled
 * compatibility signal. Never let a composing keydown invoke a command.
 */
export function isComposingKeyboardEvent(event: KeyboardEvent): boolean {
  return event.isComposing || event.key === "Process" || event.keyCode === 229;
}

export function commandAppliesToRoute(command: ProductionCommand, route: ProductionRoute): boolean {
  return command.routeScope === "global" || command.routeScope === route;
}

/** Dispatches at most one enabled command and reports whether it consumed the event. */
export function dispatchProductionCommand(
  event: KeyboardEvent,
  commands: readonly ProductionCommand[],
  context: ProductionCommandContext,
): boolean {
  if (isComposingKeyboardEvent(event)) return false;
  for (const command of commands) {
    const chords = command.chord ? [command.chord] : command.chords ?? [];
    if (chords.length === 0 || !chords.some((chord) => chordMatches(event, chord))) continue;
    if (!commandAppliesToRoute(command, context.activeRoute)) continue;
    const textEntry = isTextEntryTarget(event.target);
    if (textEntry && command.textEntryPolicy === "ignore") continue;
    if (!textEntry && command.textEntryPolicy === "text-only") continue;
    if (event.repeat && command.repeatPolicy === "ignore") continue;
    if (!command.isEnabled(context)) continue;
    event.preventDefault();
    void command.invoke(context, event);
    return true;
  }
  return false;
}

export function commandLabel(command: ProductionCommand, platform: "apple" | "other" = "other"): string {
  const chord = command.chord ?? command.chords?.[0];
  if (!chord) return "";
  const pieces: string[] = [];
  if (chord.modifier) pieces.push(platform === "apple" ? "⌘" : "Ctrl");
  if (chord.alt) pieces.push(platform === "apple" ? "⌥" : "Alt");
  if (chord.shift) pieces.push(platform === "apple" ? "⇧" : "Shift");
  pieces.push(chord.key.length === 1 ? chord.key.toLocaleUpperCase() : chord.key);
  return platform === "apple" ? pieces.join("") : pieces.join("+");
}

export function isApplePlatform(platform = typeof navigator === "undefined" ? "" : navigator.platform): boolean {
  return /Mac|iPhone|iPad|iPod/i.test(platform);
}
