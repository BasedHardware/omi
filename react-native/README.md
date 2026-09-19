This is a new [**React Native**](https://reactnative.dev) project, bootstrapped using [`@react-native-community/cli`](https://github.com/react-native-community/cli).

# Getting Started

> **Note**: Make sure you have completed the [Set Up Your Environment](https://reactnative.dev/docs/set-up-your-environment) guide before proceeding.

## Step 1: Start Metro

First, you will need to run **Metro**, the JavaScript build tool for React Native.

To start the Metro dev server, run the following command from the root of your React Native project:

```sh
# Using Bun
bun start

# OR using Yarn
yarn start
```

## Step 2: Build and run your app

With Metro running, open a new terminal window/pane from the root of your React Native project, and use one of the following commands to build and run your Android or iOS app:

### Android

```sh
# Using Bun
bun run android

# OR using Yarn
yarn android
```

### iOS

For iOS, remember to install CocoaPods dependencies (this only needs to be run on first clone or after updating native deps).

The first time you create a new project, run the Ruby bundler to install CocoaPods itself:

```sh
bundle install
```

Then, and every time you update your native dependencies, run:

```sh
bundle exec pod install
```

For more information, please visit [CocoaPods Getting Started guide](https://guides.cocoapods.org/using/getting-started.html).

```sh
# Using Bun
bun run ios

# OR using Yarn
yarn ios
```

If everything is set up correctly, you should see your new app running in the Android Emulator, iOS Simulator, or your connected device.

This is one way to run your app — you can also build it directly from Android Studio or Xcode.

## Step 3: Modify your app

Now that you have successfully run the app, let's make changes!

Open `App.tsx` in your text editor of choice and make some changes. When you save, your app will automatically update and reflect these changes — this is powered by [Fast Refresh](https://reactnative.dev/docs/fast-refresh).

When you want to forcefully reload, for example to reset the state of your app, you can perform a full reload:

- **Android**: Press the <kbd>R</kbd> key twice or select **"Reload"** from the **Dev Menu**, accessed via <kbd>Ctrl</kbd> + <kbd>M</kbd> (Windows/Linux) or <kbd>Cmd ⌘</kbd> + <kbd>M</kbd> (macOS).
- **iOS**: Press <kbd>R</kbd> in iOS Simulator.

## Congratulations! :tada:

You've successfully run and modified your React Native App. :partying_face:

### Now what?

- If you want to add this new React Native code to an existing application, check out the [Integration guide](https://reactnative.dev/docs/integration-with-existing-apps).
- If you're curious to learn more about React Native, check out the [docs](https://reactnative.dev/docs/getting-started).

# Troubleshooting

If you're having issues getting the above steps to work, see the [Troubleshooting](https://reactnative.dev/docs/troubleshooting) page.

# Learn More

To learn more about React Native, take a look at the following resources:

- [React Native Website](https://reactnative.dev) - learn more about React Native.
- [Getting Started](https://reactnative.dev/docs/environment-setup) - an **overview** of React Native and how setup your environment.
- [Learn the Basics](https://reactnative.dev/docs/getting-started) - a **guided tour** of the React Native **basics**.
- [Blog](https://reactnative.dev/blog) - read the latest official React Native **Blog** posts.
- [`@facebook/react-native`](https://github.com/facebook/react-native) - the Open Source; GitHub **repository** for React Native.

## GPT Live / react-native-webrtc

Phone GPT Live 1 uses `react-native-webrtc` on **iOS and Android only**. After
installing or upgrading that dependency, run `bundle exec pod install` inside
`react-native/ios` on a Mac (CocoaPods / Xcode are required; this Linux CI host
cannot run that step). macOS desktop builds intentionally do **not** link
WebRTC — Live stays unsupported there.

## UI review

Run `bun run --cwd pwa dev` from the repository root. The development-only
`/design-preview.html` mounts production React Native components without
persisting onboarding or bypassing authentication in the actual app. It uses
empty/unavailable data, not a live account. Use `?surface=desktop`,
`?surface=mobile`, or `?surface=mobile-setup` for the other surfaces. The default
is desktop onboarding; its Sign in action only advances the component preview.
For populated layouts, use `?surface=desktop&data=example` or
`?surface=mobile&data=example`; task edits and completion change only the
explicitly labelled local fixtures. Use
`data=empty` for successful empty reads. Neither mode makes account requests.
This entry is not included in the PWA production build.

Add `&tokens=hana` to apply the experimental Hana-inspired token treatment
(alpha-based label hierarchy and separator alphas from
`react-native/src/ui/hanaTokens.ts`; `@hana-ui/react` itself is not published).
It changes colors only — layout, materials, and interaction defaults are
untouched, and the flag defaults to off.

Desktop setup separates the AI assistant gallery from Connect data. Both are
browsable catalogs; until adapters exist, they explicitly say Coming soon and
never claim a connection. Apps retains the real account catalog under Your apps.
Permission requests remain user-initiated: the macOS command opens System
Settings for denied permissions, and React refreshes actual status on app
activation and every 1.5 seconds while the permission step is mounted.
Neither a grant nor navigation starts capture. `DesktopWindow` is an inert
React marker for the existing AppKit window: onboarding uses a compact glass
window, and requesting a permission changes it to a small companion guide.
Its text, confirmed-grant state, and Back to setup action remain React-owned.
AppKit positions it beside the measured System Settings window, follows window
movement, and floats it only while Omi or System Settings is active. When there
is no room beside Settings it yields rather than covering the controls. It does
not draw a replica switch, take screenshots, or require Accessibility access.
Leaving onboarding restores the normal app window and stops guide placement.
The existing native material honors Reduce Transparency; React transitions
honor Reduce Motion. Browser glass is only a labeled approximation.

The eight-dot mark assembles on arrival, gathers on step changes, breathes
while waiting, and bursts once on a confirmed permission grant. Clicking the
header mark replays its greeting without advancing setup. Reduced motion keeps
the ring static and moves the progress indicator immediately. The web hook
subscribes directly to `prefers-reduced-motion` so separate consumers cannot
remove one another's listeners; native uses `AccessibilityInfo`.

The main desktop keeps one shared Ask/Search/Recall field. Chat suggestions
fill and focus it without submitting; they are hidden while busy, loading, or
failed. General settings contains capture, audio, notifications, and the device
slot; backend and live-voice choices belong to AI & Automation. Desktop task
controls pass the desktop appearance explicitly, including browser previews.

Mobile keeps the composer and tab dock in layout flow so neither covers the
scrolling content. The Home mark replays its arrival greeting without changing
capture or navigation; reduced motion keeps it static. Empty/whitespace drafts
cannot submit from either the send button or the keyboard. Apps browses the
existing catalog through Explore, Installed, My Apps, and Services; installation
still waits for the backend. Native backend and live-voice choices live under
Settings → Developer. The mobile preview now mounts the real Conversations,
Settings, and Apps pages; browser-only capability restrictions still apply.

Check shared UI with `bun run --cwd react-native test -- --runInBand` and
`bun run --cwd pwa typecheck`. Review desktop at 1280×900 and compact widths,
gallery details expanded and collapsed, permissions before/after request,
mobile tabs and empty states, and reduced motion. Browser previews do not
verify native System Settings or real phone behavior; permission-pane links
and grants must also be exercised on macOS. For native review, use a dev bundle:
request and deny each permission, grant it in Settings, move Settings between
displays, switch to another app, return/skip, and sign out. Check that the guide
never covers the Settings controls, steals focus after a grant, or starts capture.
