'use client';

import { useRef, useState, useSyncExternalStore } from 'react';
import { hasOperatorToken, setOperatorToken, subscribeOperatorAccess } from '../lib/operatorAccess.mjs';

const serverSnapshot = () => false;

export default function OperatorAccess() {
  const configured = useSyncExternalStore(subscribeOperatorAccess, hasOperatorToken, serverSnapshot);
  const dialog = useRef(null);
  const [value, setValue] = useState('');
  const [error, setError] = useState('');
  const close = () => { setValue(''); setError(''); dialog.current?.close(); };

  const save = (event) => {
    event.preventDefault();
    try { setOperatorToken(value); close(); } catch (err) { setError(err.message); }
  };

  return (
    <>
      <button type="button" onClick={() => dialog.current?.showModal()}
        className="fixed bottom-4 left-4 z-[200] rounded-lg border border-white/20 bg-slate-950 px-3 py-2 text-xs text-white shadow-lg">
        {configured ? 'Operator token set' : 'Operator access'}
      </button>
      <dialog ref={dialog} onClose={() => { setValue(''); setError(''); }}
        aria-labelledby="operator-access-title"
        className="m-auto w-[min(92vw,420px)] rounded-xl border border-slate-600 bg-slate-950 p-6 text-white backdrop:bg-black/70">
        <form onSubmit={save}>
          <h2 id="operator-access-title" className="text-lg font-semibold">Operator access</h2>
          <p className="my-3 text-sm text-slate-300">Read-only dashboards are public. Analysis and collection require the server operator token. It stays in this tab’s memory and clears on reload.</p>
          <label htmlFor="operator-token" className="block text-sm">Operator token</label>
          <input id="operator-token" type="password" autoComplete="off" spellCheck={false}
            value={value} onChange={(event) => setValue(event.target.value)} required minLength={32}
            className="mt-2 w-full rounded border border-slate-600 bg-slate-900 p-2" />
          {error && <p role="alert" className="mt-2 text-sm text-red-300">{error}</p>}
          <div className="mt-4 flex gap-3 text-sm">
            <button type="submit" className="rounded bg-blue-700 px-3 py-2">Use token</button>
            {configured && <button type="button" onClick={() => { setOperatorToken(''); close(); }} className="rounded border px-3 py-2">Clear token</button>}
            <button type="button" onClick={close} className="ml-auto px-3 py-2">Close</button>
          </div>
        </form>
      </dialog>
    </>
  );
}
