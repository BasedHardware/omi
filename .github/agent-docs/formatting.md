# Formatting

The pre-commit hook installed by `make setup` auto-formats staged files, so in normal
work you should not need to run anything here. Verify the hook is live:

```bash
test -x "$(git rev-parse --git-path hooks)/pre-commit" && echo OK
```

In a merge commit the hook skips files staged exactly as the incoming side has them, so
merging `main` does not reformat main's files; resolved conflicts are still formatted.
Dart formatting needs `app/.dart_tool/package_config.json` (run `flutter pub get` in
`app/`): without it `dart format` ignores the package language version and the hook refuses.

Run a formatter by hand only when the hook is unavailable (some CI and sandbox
environments) or when you are formatting files you have not staged.

| Language | Manual command |
|----------|----------------|
| Dart (`app/`) | `dart format --line-length 120 <files>` |
| Python (`backend/`) | `scripts/backend-python-format --write <files>` |
| ARB (`app/lib/l10n/`) | `jq --indent 4 '.' <file> > tmp && mv tmp <file>` |
| C/C++ (firmware) | `clang-format -i <files>` |
| Swift (`desktop/macos/Desktop/`) | `desktop/macos/scripts/swift-format-wrapper.sh format -i <files>` |
| Web (`web/`) | `npx prettier --write <files>` |

## Never format these

- Generated Dart: files ending in `.gen.dart` or `.g.dart`.
- Generated Swift: anything under `desktop/macos/Desktop/Sources/Generated/`, which is
  excluded from the formatter's own scope.

Regenerate these through their codegen step instead; see the component guide.
