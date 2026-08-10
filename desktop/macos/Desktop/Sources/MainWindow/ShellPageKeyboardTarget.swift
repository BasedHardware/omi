//
//  ShellPageKeyboardTarget.swift — a page that answers keys, without tracing the window in blue.
//
//  Same defect family as `ShellModalScrim`, and a different mechanism, so it is worth stating the
//  shared cause once: **the shell window has no visible extent.** `ShellWindowChrome` took the ground
//  away, so the window is a transparent rectangle noticeably larger than the panels floating inside
//  it. Anything drawn at window scale — a fill, a shadow, or a *stroke* — lands on the user's
//  wallpaper in the shape of a window that is not there.
//
//  The scrim was the fill. This is the stroke, and nobody wrote it: a page that wants to answer
//  `↑ ↓ ← →` anywhere on itself has to be `focusable()`, and AppKit draws a focus effect around
//  whatever holds keyboard focus. On a button that is the whole point of the effect. On a container
//  the size of the shell's content area it is a 1 pt system-accent rectangle traced along the window's
//  left, right and bottom edges with a full-width line under the top bar — reported from a live build
//  as "Rewind draws a blue rectangle on my wallpaper". It is also the *system accent*, the one hue
//  this product does not use anywhere (INV-UI-1).
//
//  ## Why the two modifiers travel together
//
//  Because they only make sense together, and one of them is invisible until it is wrong. A focus
//  effect communicates *which control* the keyboard is aimed at; a page is not a control, so at page
//  scale the effect has nothing to say and the only thing it does is paint. The onboarding host
//  reached the same conclusion independently and writes the pair inline (`OnboardingView`). Rewind
//  wrote only the first half, which is exactly the shape of miss a named pair exists to stop: the
//  focusable part is the part you notice missing, and the effect is the part you notice shipping.
//
//  Focus itself is untouched — the page still takes it, still holds it, and every key handler on it
//  still fires. What is removed is a paint, not a behaviour.
//
//  Brand: nothing here picks a colour; it removes one the system picked (INV-UI-1).
//

import SwiftUI

extension View {
  /// Makes this view the page's keyboard target: focusable, bound to the page's focus state, and
  /// drawing no system focus effect.
  ///
  /// For containers at page or content-area scale — the ones whose `onKeyPress` / `onScrollWheel`
  /// handlers need to fire wherever the pointer is. A real control should keep its focus effect;
  /// that is what tells a keyboard user where they are.
  ///
  /// `focusEffectDisabled()` is an environment value, so it reaches this subtree. That is the
  /// intended scope here: the shell's pages style their own controls (`.buttonStyle(.plain)`,
  /// `.textFieldStyle(.plain)`) and carry their own hover and selection treatments, so there is no
  /// system-drawn ring underneath to lose. A descendant that genuinely wants one asks with
  /// `focusEffectDisabled(false)`.
  func shellPageKeyboardTarget(_ focus: FocusState<Bool>.Binding) -> some View {
    self
      .focusable()
      .focusEffectDisabled()
      .focused(focus)
  }
}
