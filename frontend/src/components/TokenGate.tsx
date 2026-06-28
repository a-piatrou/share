/**
 * TokenGate — wraps internal pages that require a bearer token (RBAC).
 * Shows a token entry form until a token is stored in session.
 */
import { useState } from "react";
import type { ReactNode } from "react";

interface Props {
  token: string;
  onSetToken: (t: string) => void;
  children: ReactNode;
}

export function TokenGate({ token, onSetToken, children }: Props) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");

  if (token) {
    return <>{children}</>;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim()) {
      setError("Token is required");
      return;
    }
    onSetToken(draft.trim());
  }

  return (
    <div className="min-h-[70vh] flex items-center justify-center">
      <div className="gw-card w-full max-w-md">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-8 h-8 rounded-lg bg-gw-teal-dim flex items-center justify-center">
            <svg className="w-4 h-4 text-gw-teal" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <div>
            <h2 className="text-base font-semibold text-gw-text">Internal Access</h2>
            <p className="text-xs text-gw-subtle">RBAC-protected endpoint</p>
          </div>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="gw-label" htmlFor="token">Bearer Token</label>
            <input
              id="token"
              type="password"
              className="gw-input font-mono text-sm"
              placeholder="sk-ant-…"
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                setError("");
              }}
              autoFocus
            />
            {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
          </div>
          <button type="submit" className="gw-btn-primary w-full justify-center">
            Authenticate
          </button>
        </form>
        <p className="mt-4 text-2xs text-gw-subtle text-center">
          Token stored in sessionStorage only — cleared on tab close.
        </p>
      </div>
    </div>
  );
}
