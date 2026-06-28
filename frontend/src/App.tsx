/**
 * GHOSTWIRE frontend — root router.
 * Three surfaces per REQ-015:
 *   /          — public chat widget (POST /chat/query, no auth)
 *   /feedback  — internal feedback dashboard (POST /feedback/analyze, RBAC)
 *   /team      — internal team assembly UI (POST /team/assemble, RBAC)
 */
import { Routes, Route } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { ChatPage } from "@/pages/Chat";
import { FeedbackPage } from "@/pages/Feedback";
import { TeamPage } from "@/pages/Team";

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <span className="text-4xl font-mono font-bold text-gw-muted">404</span>
      <p className="text-gw-subtle text-sm">Page not found</p>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<ChatPage />} />
        <Route path="feedback" element={<FeedbackPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
