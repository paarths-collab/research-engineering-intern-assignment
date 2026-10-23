'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { safeNextPath, signIn, signUp } from '../lib/authClient.mjs';
import { useAuth } from './AuthProvider';

export default function AccountForm({ mode, nextPath }) {
  const signup = mode === 'signup';
  const router = useRouter();
  const { user, configured, refreshSession } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const next = safeNextPath(nextPath);

  async function submit(event) {
    event.preventDefault();
    setError('');
    if (signup && password !== confirmPassword) { setError('Your passwords do not match.'); return; }
    setBusy(true);
    try {
      await (signup ? signUp(email, password) : signIn(email, password));
      setPassword('');
      setConfirmPassword('');
      const account = await refreshSession();
      if (!account) throw new Error('Sign-in could not be completed. Please try again.');
      router.replace(next);
      router.refresh();
    } catch (err) {
      setPassword('');
      setConfirmPassword('');
      setError(err.message || 'Account access is temporarily unavailable. Please try again later.');
    } finally { setBusy(false); }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#0a0806] px-5 py-28">
      <section aria-labelledby="account-title" className="w-full max-w-md border border-[#FFB800]/20 bg-[#151009] p-7 shadow-2xl sm:p-10">
        <Link href="/" className="font-mono text-[10px] uppercase tracking-[0.3em] text-[#FFB800]">NarrativeSignal</Link>
        <h1 id="account-title" className="mt-6 font-manrope text-3xl font-semibold text-white">{signup ? 'Create your account' : 'Welcome back'}</h1>
        <p className="mt-3 text-sm leading-6 text-white/65">{signup ? 'Sign up to explore narratives and run analysis with your own account.' : 'Sign in to run analysis and explore the stories behind the data.'}</p>
        {user ? (
          <div className="mt-6 space-y-4 text-sm">
            <p className="break-all text-white/80">Signed in as {user.email}.</p>
            <Link href={next} className="inline-block bg-[#FFB800] px-5 py-3 font-semibold text-black">Continue to analysis</Link>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-7 space-y-5">
            <div>
              <label htmlFor="account-email" className="block text-sm text-white/90">Email address</label>
              <input id="account-email" name="email" type="email" autoComplete="email" required maxLength={320}
                value={email} onChange={(event) => setEmail(event.target.value)} disabled={busy}
                className="mt-2 w-full border border-white/20 bg-black/30 px-3 py-3 text-base text-white outline-none focus:border-[#FFB800] disabled:opacity-60" />
            </div>
            <div>
              <label htmlFor="account-password" className="block text-sm text-white/90">Password</label>
              <input id="account-password" name="password" type="password" autoComplete={signup ? 'new-password' : 'current-password'} required
                minLength={signup ? 12 : undefined} maxLength={128} aria-describedby={signup ? 'password-help' : undefined}
                value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy}
                className="mt-2 w-full border border-white/20 bg-black/30 px-3 py-3 text-base text-white outline-none focus:border-[#FFB800] disabled:opacity-60" />
              {signup ? <p id="password-help" className="mt-2 text-xs text-white/55">Use 12 to 128 characters. Choose a password you don’t use elsewhere.</p> : null}
            </div>
            {signup ? <div>
              <label htmlFor="account-confirm-password" className="block text-sm text-white/90">Confirm password</label>
              <input id="account-confirm-password" name="confirmPassword" type="password" autoComplete="new-password" required minLength={12} maxLength={128}
                value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} disabled={busy}
                className="mt-2 w-full border border-white/20 bg-black/30 px-3 py-3 text-base text-white outline-none focus:border-[#FFB800] disabled:opacity-60" />
            </div> : null}
            {configured === false ? <p role="status" className="text-sm leading-6 text-amber-200">Account access is being set up. Please try again shortly. Public dashboards remain available.</p> : null}
            {error ? <p role="alert" className="text-sm leading-6 text-red-300">{error}</p> : null}
            <button type="submit" disabled={busy || configured === false} className="w-full bg-[#FFB800] px-4 py-3 text-sm font-bold text-black transition hover:bg-[#ffd16b] disabled:cursor-not-allowed disabled:opacity-50">
              {busy ? (signup ? 'Creating account…' : 'Signing in…') : (signup ? 'Create account' : 'Sign in')}
            </button>
          </form>
        )}
        <p className="mt-6 text-sm text-white/60">{signup ? 'Already have an account? ' : 'New to NarrativeSignal? '}
          <Link href={`/${signup ? 'login' : 'signup'}?next=${encodeURIComponent(next)}`} className="text-[#FFB800] underline underline-offset-4">{signup ? 'Sign in' : 'Create an account'}</Link>
        </p>
        <Link href="/overview" className="mt-6 inline-block text-xs text-white/55 underline underline-offset-4">Browse the public dashboards</Link>
      </section>
    </main>
  );
}
