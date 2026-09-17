import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { ApiError, getMe, type MeResponse, type ProfileSummary, type User } from './api';

export interface MeState {
  user: User | null;
  profile: ProfileSummary | null;
  /** true until the one-and-only /api/me fetch settles. */
  loading: boolean;
  /** Replace the cached value after sign-in, PATCH /me, triggers, etc. */
  setMe: (me: MeResponse | null) => void;
  setProfile: (profile: ProfileSummary) => void;
  /** Force a re-fetch (after sign-in or account changes). */
  refresh: () => Promise<void>;
}

const MeContext = createContext<MeState | null>(null);

export function MeProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfileState] = useState<ProfileSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const fetched = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const me = await getMe();
      setUser(me.user);
      setProfileState(me.profile);
    } catch (err) {
      // A signed-out visitor gets 401 here; that is expected, not an error.
      if (!(err instanceof ApiError)) throw err;
      setUser(null);
      setProfileState(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (fetched.current) return;
    fetched.current = true;
    void load();
  }, [load]);

  const setMe = useCallback((me: MeResponse | null) => {
    setUser(me?.user ?? null);
    setProfileState(me?.profile ?? null);
    setLoading(false);
  }, []);

  const value = useMemo<MeState>(
    () => ({
      user,
      profile,
      loading,
      setMe,
      setProfile: setProfileState,
      refresh: load,
    }),
    [user, profile, loading, setMe, load],
  );

  return <MeContext.Provider value={value}>{children}</MeContext.Provider>;
}

export function useMe(): MeState {
  const ctx = useContext(MeContext);
  if (!ctx) throw new Error('useMe must be used inside <MeProvider>');
  return ctx;
}
