import { createContext, useContext, useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import SuperTokens, { SuperTokensWrapper } from "supertokens-auth-react";
import { getSuperTokensRoutesForReactRouterDom } from "supertokens-auth-react/ui";
import { EmailPasswordPreBuiltUI } from "supertokens-auth-react/recipe/emailpassword/prebuiltui";
import * as reactRouterDom from "react-router-dom";
import { SuperTokensConfigObj } from "./auth/config";
import { ProtectedRoute } from "./routes/ProtectedRoute";
import { Nav } from "./components/Nav";
import { Backdrop } from "./components/ui";
import { Overview } from "./pages/Overview";
import { Sensors } from "./pages/Sensors";
import { Investigations } from "./pages/Investigations";
import { LiveStation } from "./pages/LiveStation";
import { FaultLibrary } from "./pages/FaultLibrary";
import { FaultLab } from "./pages/FaultLab";
import { About } from "./pages/About";
import { Admin } from "./pages/Admin";
import { api, type Me } from "./api/client";
import "./theme.css";

SuperTokens.init(SuperTokensConfigObj);

export const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

function AppShell() {
  const [me, setMe] = useState<Me | null>(null);
  const [model, setModel] = useState<Record<string, any> | null>(null);

  useEffect(() => { api.me().then(setMe).catch(() => setMe(null)); }, []);

  return (
    <MeContext.Provider value={me}>
      <Backdrop />
      <div className="shell">
        <Nav me={me} />
        <main className="container">
          <Routes>
            <Route path="/" element={<Overview me={me} model={model} onModel={setModel} />} />
            <Route path="/sensors" element={<Sensors />} />
            <Route path="/investigations" element={<Investigations />} />
            <Route path="/live" element={<LiveStation />} />
            <Route path="/faults" element={<FaultLibrary />} />
            <Route path="/lab" element={<FaultLab />} />
            {/* About hub — the four legacy content routes each open their own section. */}
            <Route path="/about" element={<About />} />
            <Route path="/overview" element={<About />} />
            <Route path="/problem" element={<About />} />
            <Route path="/how" element={<About />} />
            <Route path="/plan" element={<About />} />
            {/* /admin stays mounted for every user; the API returns 403 to non-admins. */}
            <Route path="/admin" element={<Admin />} />
          </Routes>
        </main>
        <footer>
          <div className="container footin">
            <span>SkyGuard AI · SIH 26073 · Ministry of Earth Sciences / IMD</span>
            <span>
              Automated anomaly assessment — requires human verification.
              {model?.model_version && <> Model <span className="mono">{model.model_version}</span></>}
            </span>
          </div>
        </footer>
      </div>
    </MeContext.Provider>
  );
}

export default function App() {
  return (
    <SuperTokensWrapper>
      <BrowserRouter>
        <Routes>
          {getSuperTokensRoutesForReactRouterDom(reactRouterDom, [EmailPasswordPreBuiltUI])}
          <Route path="/*" element={<ProtectedRoute><AppShell /></ProtectedRoute>} />
        </Routes>
      </BrowserRouter>
    </SuperTokensWrapper>
  );
}
