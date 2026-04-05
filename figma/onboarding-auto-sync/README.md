OMI onboarding auto sync is a Figma development plugin.

Install:
1. In Figma, open `Plugins` > `Development` > `Import plugin from manifest...`
2. Select [manifest.json](/Users/nik/projects/omi-onboarding-figma-sync/figma/onboarding-auto-sync/manifest.json)
3. Run `Plugins` > `Development` > `OMI Onboarding Auto Sync` while focused on the target page.

What it does:
- Polls `https://raw.githubusercontent.com/BasedHardware/omi/figma-onboarding-sync/onboarding/latest/manifest.json`
- Rewrites a frame named `Onboarding Sync` on the current page
- Keeps polling every 15 seconds until the plugin is stopped or the Figma session ends

The GitHub workflow that publishes the source bundle is [onboarding_figma_sync.yml](/Users/nik/projects/omi-onboarding-figma-sync/.github/workflows/onboarding_figma_sync.yml).
