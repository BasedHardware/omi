# ADR 0001: Package architecture

**Status:** accepted (2026-10-06)

Layered Swift packages, dependency direction enforced by SPM:
`OmiCore ← OmiNetwork ← OmiPersistence ← OmiService ← OmiDesign ← OmiFeatures ← App`.

- Template: IrisNew `persona_dev` (XcodeGen, Swift 6 strict concurrency, `@MainActor @Observable`
  stores, one `AppEnvironment` composition root).
- Deliberate differences from the template: stores depend on `APIClientProtocol` (testable with
  `FakeAPIClient`), no singletons, one SPM target per feature (features cannot import each other;
  only the app shell composes them), files kept under ~400 lines.
- `OmiNetwork` (not `OmiAPI`): the upstream Swift DTO generator namespaces every wire type under
  `enum OmiAPI`, which would collide with a module of the same name.
- Wire DTOs never leave `OmiNetwork`; mappers adapt them to `OmiCore` domain models.
