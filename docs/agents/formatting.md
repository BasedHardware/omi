# Formatting

The pre-commit hook installed by `make setup` auto-formats staged files, so in normal
work you should not need to run anything here. Verify the hook is live:

```bash
test -x "$(git rev-parse --git-path hooks)/pre-commit" && echo OK
```

Run a formatter by hand only when the hook is unavailable (some CI and sandbox
environments) or when you are formatting files you have not staged.

| Language | Manual command |
|----------|----------------|
| Dart (`app/`) | `dart format --line-length 120 <files>` |
| Python (`backend/`) | `black --line-length 120 --skip-string-normalization <files>` |
| ARB (`app/lib/l10n/`) | `jq --indent 4 '.' <file> > tmp && mv tmp <file>` |
| C/C++ (firmware) | `clang-format -i <files>` |
| Rust (`desktop/macos/Backend-Rust/`) | `rustfmt --edition 2021 <files>` |
| Swift (`desktop/macos/Desktop/`) | `desktop/macos/scripts/swift-format-wrapper.sh format -i <files>` |
| Web (`web/`) | `npx prettier --write <files>` |

## Never format these

- Generated Dart: files ending in `.gen.dart` or `.g.dart`.
- Generated Swift: anything under `desktop/macos/Desktop/Sources/Generated/`, which is
  excluded from the formatter's own scope.

Regenerate these through their codegen step instead; see the component guide.
