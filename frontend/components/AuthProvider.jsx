'use client';

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { getAuthStatus, getCurrentUser, signOut, subscribeAuthRequired } from '../lib/authClient.mjs';
import { setOperatorToken } from '../lib/operatorAccess.mjs';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [configured, setConfigured] = useState(null);
  const [notice, setNotice] = useState('');
  const sessionRequest = useRef(0);

  const refreshSession = useCallback(async () => {
    const request = ++sessionRequest.current;
    const nextUser = await getCurrentUser();
    if (request === sessionRequest.current) {
      setUser(nextUser);
      if (nextUser) setNotice('');
    }
    return nextUser;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const request = ++sessionRequest.current;
    Promise.allSettled([
      getCurrentUser({ signal: controller.signal }),
      getAuthStatus({ signal: controller.signal }),
    ]).then(([session, status]) => {
      if (controller.signal.aborted) return;
      if (session.status === 'fulfilled' && request === sessionRequest.current) setUser(session.value);
      if (status.status === 'fulfilled') setConfigured(status.value.configured === true);
      setLoading(false);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => subscribeAuthRequired(() => {
    setUser(null);
    setNotice('Sign in to run analysis.');
    refreshSession().catch(() => { /* The sign-in link remains available if the API is offline. */ });
  }), [refreshSession]);

  const logout = useCallback(async () => {
    setOperatorToken('');
    ++sessionRequest.current;
    await signOut();
    setUser(null);
    setNotice('');
  }, []);

  return <AuthContext.Provider value={{ user, loading, configured, notice, refreshSession, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('Account access requires AuthProvider.');
  return context;
}
