// Preview-only side effect. Imported FIRST by design-preview.ts so the
// experimental Hana-inspired token overrides land before any component module
// resolves its StyleSheet values. Does nothing without ?tokens=hana, and this
// entry is excluded from the PWA production build.
import { applyHanaTokens } from "../../react-native/src/ui/hanaTokens";

if (new URLSearchParams(location.search).get("tokens") === "hana") {
  applyHanaTokens();
  document.body.dataset.tokens = "hana";
}
