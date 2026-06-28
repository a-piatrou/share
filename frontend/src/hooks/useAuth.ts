/**
 * Simple bearer-token store for RBAC-protected internal pages.
 * In production this would be replaced by a proper OIDC/OAuth flow.
 * For MVP: token is stored in sessionStorage and entered manually.
 */
import { useState, useCallback } from "react";

const SESSION_KEY = "gw_bearer_token";

export function useAuth() {
  const [token, setTokenState] = useState<string>(
    () => sessionStorage.getItem(SESSION_KEY) ?? "",
  );

  const setToken = useCallback((t: string) => {
    sessionStorage.setItem(SESSION_KEY, t);
    setTokenState(t);
  }, []);

  const clearToken = useCallback(() => {
    sessionStorage.removeItem(SESSION_KEY);
    setTokenState("");
  }, []);

  return { token, setToken, clearToken, isAuthenticated: token.length > 0 };
}
