# Localization PRD v3 - Missing Translations & Hardcoded Strings

## Overview

This document tracks the third phase of localization work for the Omi Flutter app. It covers:
1. Missing translation keys in existing ARB files (keys present in English but missing in other languages)
2. Hardcoded strings in Dart code that need localization

## Status: IN PROGRESS

---

## Part 1: Missing ARB Translation Keys

### Summary

Total languages with missing translations: **31**

| Language | Code | Missing Keys | Priority |
|----------|------|--------------|----------|
| Czech | cs | 31 | HIGH |
| Danish | da | 31 | HIGH |
| Arabic | ar | 8 | MEDIUM |
| Bulgarian | bg | 8 | MEDIUM |
| Catalan | ca | 8 | MEDIUM |
| German | de | 8 | MEDIUM |
| Greek | el | 22 | HIGH |
| Spanish | es | 22 | HIGH |
| Estonian | et | 22 | HIGH |
| Finnish | fi | 22 | HIGH |
| French | fr | 22 | HIGH |
| Hindi | hi | 22 | HIGH |
| Hungarian | hu | 22 | HIGH |
| Indonesian | id | 22 | HIGH |
| Italian | it | 22 | HIGH |
| Japanese | ja | 22 | HIGH |
| Korean | ko | 22 | HIGH |
| Lithuanian | lt | 22 | HIGH |
| Latvian | lv | 22 | HIGH |
| Malay | ms | 22 | HIGH |
| Dutch | nl | 22 | HIGH |
| Norwegian | no | 22 | HIGH |
| Polish | pl | 22 | HIGH |
| Portuguese | pt | 22 | HIGH |
| Romanian | ro | 22 | HIGH |
| Russian | ru | 22 | HIGH |
| Slovak | sk | 22 | HIGH |
| Swedish | sv | 22 | HIGH |
| Thai | th | 22 | HIGH |
| Turkish | tr | 22 | HIGH |
| Chinese | zh | 22 | HIGH |

### Missing Keys Breakdown

#### Group A: 31 missing keys (cs, da)
```
autoClosingInSeconds
availableSpace
batteryDrainIncrease
debugModeDetected
deviceNotCompatible
deviceRequirements
download
downloadError
downloadModel
downloadWhisperModel
downloading
editReply
estimatedSize
failedToSendReply
largeModelWarning
localProcessingInfo
model
modelReady
modelRequired
noModelDownloadRequired
noReviewsFound
onDeviceIntensive
onDeviceSlower
performanceReduced
premiumMinutesInfo
redownload
reply
replySentSuccessfully
send
starFilter
writeYourReply
```

#### Group B: 22 missing keys (el, es, et, fi, fr, hi, hu, id, it, ja, ko, lt, lv, ms, nl, no, pl, pt, ro, ru, sk, sv, th, tr, zh)
```
availableSpace
batteryDrainIncrease
deviceRequirements
downloadError
editReply
estimatedSize
failedToSendReply
largeModelWarning
localProcessingInfo
model
modelReady
noModelDownloadRequired
noReviewsFound
onDeviceIntensive
onDeviceSlower
premiumMinutesInfo
redownload
reply
replySentSuccessfully
send
starFilter
writeYourReply
```

#### Group C: 8 missing keys (ar, bg, ca, de)
```
editReply
failedToSendReply
noReviewsFound
reply
replySentSuccessfully
send
starFilter
writeYourReply
```

---

## Part 2: Hardcoded Strings in Dart Code

### Files Requiring Localization

#### 1. fast_transfer_suggestion_dialog.dart
**Path:** `app/lib/pages/conversations/sync_widgets/fast_transfer_suggestion_dialog.dart`

| Line | Hardcoded String | Suggested Key |
|------|------------------|---------------|
| 19 | `'Choose Transfer Method'` | `chooseTransferMethod` |
| 50 | `'Fast Transfer'` | `fastTransfer` |
| 55 | `'~150 KB/s via WiFi'` | `fastTransferSpeed` |
| 92 | `'Bluetooth'` | `bluetooth` |
| 97 | `'~30 KB/s via BLE'` | `bluetoothSpeed` |

#### 2. merge_confirmation_dialog.dart
**Path:** `app/lib/pages/conversations/widgets/merge_confirmation_dialog.dart`

| Line | Hardcoded String | Suggested Key |
|------|------------------|---------------|
| 165 | `'Large time gap detected (${gaps.first})'` | `largeTimeGapDetected` |
| 167 | `'Large time gaps detected (${gaps.join(", ")})'` | `largeTimeGapsDetected` |

---

## Implementation Plan

### Phase 1: Add Missing Keys to ARB Files
1. Add 31 keys to cs, da
2. Add 22 keys to el, es, et, fi, fr, hi, hu, id, it, ja, ko, lt, lv, ms, nl, no, pl, pt, ro, ru, sk, sv, th, tr, zh
3. Add 8 keys to ar, bg, ca, de

### Phase 2: Localize Hardcoded Strings
1. Add 7 new keys to app_en.arb
2. Update Dart files to use context.l10n
3. Add translations to all 33 language ARB files

### Phase 3: Verification
1. Run `flutter gen-l10n` to regenerate localization files
2. Run `app/test.sh` to verify no issues
3. Test app in different locales

---

## Completion Criteria

- [ ] All 31 languages have complete translations matching English keys
- [ ] All hardcoded strings in Dart code replaced with context.l10n calls
- [ ] flutter gen-l10n runs without errors
- [ ] app/test.sh passes

---

## Created
Date: 2026-01-21
Version: 3.0
