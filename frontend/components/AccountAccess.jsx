'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { useAuth } from './AuthProvider';
import { safeNextPath } from '../lib/authClient.mjs';

export default function AccountAccess() {
  const { user, loading, notice, logout } = useAuth();
  const pathname = usePathname();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const next = encodeURIComponent(safeNextPath(pathname));

  async function handleSignOut() {
    setBusy(true);
    setError('');
    try { await logout(); } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return (
    <aside aria-label="Account access" className="fixed bottom-4 left-4 z-[200] max-w-[calc(100vw-2rem)] border border-[#FFB800]/25 bg-[#0a0806]/95 px-4 py-3 text-xs text-[#f0eae6] shadow-xl backdrop-blur">
      {loading ? <span className="text-white/60" role="status">Checking account…</span> : user ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="max-w-[min(60vw,250px)] truncate" title={user.email}>{user.email}</span>
          <button type="button" onClick={handleSignOut} disabled={busy} className="text-[#FFB800] underline underline-offset-4 disabled:opacity-50">{busy ? 'Signing out…' : 'Sign out'}</button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <Link href={`/login?next=${next}`} className="text-[#FFB800] underline underline-offset-4">Sign in</Link>
          <Link href={`/signup?next=${next}`} className="text-white/80 hover:text-white">Create account</Link>
        </div>
      )}
      {notice && !user ? <p role="status" className="mt-2 text-white/70">{notice}</p> : null}
      {error ? <p role="alert" className="mt-2 max-w-xs text-red-300">{error}</p> : null}
    </aside>
  );
}
