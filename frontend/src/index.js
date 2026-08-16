import { Buffer } from 'buffer';
import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";

// Build target is fixed at compile time, so this is a static condition rather than a
// runtime branch. Webpack evaluates it during the build and dead-code-eliminates the
// branch that is not taken, along with everything that branch imports. The holders
// bundle therefore contains no admin code at all — not disabled, absent.
//
//   holders.yabbai.network  ->  REACT_APP_BUILD_TARGET=holders
//   token.yabbai.network    ->  unset (full command app)
const IS_HOLDERS_BUILD = process.env.REACT_APP_BUILD_TARGET === 'holders';

// Polyfill Buffer for @solana/web3.js (command build only needs it, but it is
// harmless and tiny).
if (typeof window !== 'undefined') {
  window.Buffer = window.Buffer || Buffer;
}

const root = ReactDOM.createRoot(document.getElementById("root"));

if (IS_HOLDERS_BUILD) {
  const HoldersApp = require("@/HoldersApp").default;
  root.render(
    <React.StrictMode>
      <HoldersApp />
    </React.StrictMode>,
  );
} else {
  const App = require("@/App").default;
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}
