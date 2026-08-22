import React from "react";
import { AppRegistry } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import App from "../../react-native/App";
import "./root.css";

const rootTag = document.querySelector<HTMLDivElement>("#app");
if (rootTag === null) throw new Error("PWA app root is missing");

const Root = (props: { initialRoute?: string }) =>
  React.createElement(SafeAreaProvider, null, React.createElement(App, props));

AppRegistry.registerComponent("RnRuntime", () => Root);
AppRegistry.runApplication("RnRuntime", { rootTag });

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => undefined);
}
