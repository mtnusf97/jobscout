import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import AdHocPage from "./pages/AdHocPage";
import JobsPage from "./pages/JobsPage";
import ProfileDetail from "./pages/ProfileDetail";
import Profiles from "./pages/Profiles";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="/profiles" element={<Profiles />} />
          <Route path="/profiles/:id" element={<ProfileDetail />} />
          <Route path="/profiles/:id/jobs" element={<JobsPage />} />
          <Route path="/profiles/:id/adhoc" element={<AdHocPage />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
