# Desktop Update Policy

Use this when macOS desktop users need an extra update prompt beyond Sparkle.

## Firestore Config

Create or update `desktop_update_policy/current`:

```json
{
  "active": true,
  "severity": "required",
  "maximum_build_number": 11507,
  "latest_build_number": 11590,
  "title": "Update required",
  "message": "Your Omi desktop app has an older updater issue. Please install the latest version manually.",
  "cta_text": "Download latest",
  "download_url": "https://api.omi.me/v2/desktop/download/latest?channel=stable",
  "can_dismiss": false,
  "platforms": ["macos"]
}
```

## Fields

- `active`: `true` enables the policy.
- `severity`: `banner` shows a dismissible top banner; `required` shows a blocking prompt; `none` disables it.
- `maximum_build_number`: highest client build that should see the policy. Clients above this build do not see it.
- `latest_build_number`: informational for clients and analytics.
- `title`, `message`, `cta_text`: user-facing copy.
- `download_url`: manual installer URL.
- `can_dismiss`: only applies to `banner`; required prompts cannot be dismissed.
- `platforms`: optional allowlist. Omit or use `["macos"]` for macOS.

## Verification

```bash
curl 'https://api.omi.me/v2/desktop/update-policy?platform=macos&current_build=11400'
curl 'https://api.omi.me/v2/desktop/appcast.xml?platform=macos' | grep criticalUpdate
```

Disable the policy by setting `active` to `false`.
