import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { authApi, AUTH_TOKEN_KEY, type AuthUser } from "@/lib/api";

type Ctx = {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const AuthCtx = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() =>
    typeof window !== "undefined" ? localStorage.getItem(AUTH_TOKEN_KEY) : null
  );
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState<boolean>(!!token);

  const persistToken = useCallback((t: string | null) => {
    if (t) localStorage.setItem(AUTH_TOKEN_KEY, t);
    else localStorage.removeItem(AUTH_TOKEN_KEY);
    setToken(t);
  }, []);

  const refresh = useCallback(async () => {
    if (!localStorage.getItem(AUTH_TOKEN_KEY)) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await authApi.me();
      setUser(me.user);
    } catch {
      persistToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [persistToken]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await authApi.login({ email, password });
      persistToken(res.access_token);
      setUser(res.user);
    },
    [persistToken]
  );

  const register = useCallback(
    async (email: string, password: string, fullName?: string) => {
      const res = await authApi.register({
        email,
        password,
        full_name: fullName,
      });
      persistToken(res.access_token);
      setUser(res.user);
    },
    [persistToken]
  );

  const logout = useCallback(() => {
    persistToken(null);
    setUser(null);
    if (typeof window !== "undefined") window.location.assign("/login");
  }, [persistToken]);

  const value = useMemo<Ctx>(
    () => ({ user, token, loading, login, register, logout, refresh }),
    [user, token, loading, login, register, logout, refresh]
  );
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
