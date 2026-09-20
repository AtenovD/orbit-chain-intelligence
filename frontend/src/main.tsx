import { Component, StrictMode, type ErrorInfo, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import * as Sentry from "@sentry/react";
import "reactflow/dist/style.css";
import "@fontsource/manrope/latin-400.css";
import "@fontsource/manrope/latin-500.css";
import "@fontsource/manrope/latin-600.css";
import "@fontsource/manrope/latin-700.css";
import "@fontsource/manrope/cyrillic-400.css";
import "@fontsource/manrope/cyrillic-500.css";
import "@fontsource/manrope/cyrillic-600.css";
import "@fontsource/manrope/cyrillic-700.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/jetbrains-mono/latin-500.css";
import "@fontsource/jetbrains-mono/latin-600.css";
import "@fontsource/jetbrains-mono/cyrillic-400.css";
import "@fontsource/jetbrains-mono/cyrillic-500.css";
import "@fontsource/jetbrains-mono/cyrillic-600.css";
import "./styles.css";
import "./connections.css";
import "./chat-memory.css";
import "./ux-tweaks.css";
import "./api-wizard.css";
import "./experience.css";
import "./agent-skill.css";
import "./skills-marketplace.css";
import "./github-connector.css";
import "./mcp-hub.css";
import "./deep-research.css";
import "./agent-growth.css";
import "./holo-mode.css";
import "./feedback-effects.css";
import "./selection-controls.css";
import "./mobile-polish.css";
import "./dialogue-context.css";
import "./cinematic-home.css";
import "./preset-modules.css";
import "./profile.css";
import "./completion-audit.css";
import "./material-control.css";
import "./killer-loop.css";
import "./dialogue-automation.css";
import "./dialogue-fixes.css";
import "./signal-room.css";
import "./orbit-system.css";
import App from "./App";

const sentryDsn = import.meta.env.VITE_SENTRY_DSN;
if (sentryDsn) {
  Sentry.init({ dsn: sentryDsn, environment: import.meta.env.MODE, sendDefaultPii: false, tracesSampleRate: 0.05 });
}

class OrbitErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) {
    if (sentryDsn) Sentry.captureException(error, { extra: { componentStack: info.componentStack } });
  }
  render() {
    if (this.state.failed) return <main className="fatal-screen"><div className="brandmark" /><p className="eyebrow">ORBIT // RECOVERY MODE</p><h1>We hit turbulence.</h1><p>The workspace did not load safely. Refresh to try again.</p><button onClick={() => location.reload()}>Reload Orbit</button></main>;
    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(<StrictMode><OrbitErrorBoundary><App /></OrbitErrorBoundary></StrictMode>);
