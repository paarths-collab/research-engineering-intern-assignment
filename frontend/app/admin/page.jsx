import OperatorAccess from '../../components/OperatorAccess';

export const metadata = { title: 'Admin | NarrativeSignal', robots: { index: false, follow: false } };

export default function AdminPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#0a0806] px-5 py-28">
      <section className="w-full max-w-lg border border-[#FFB800]/20 bg-[#151009] p-8">
        <h1 className="font-manrope text-2xl font-semibold text-white">Admin access</h1>
        <p className="my-4 text-sm leading-6 text-white/65">Collection and diagnostics are admin only. Enter your private operator token to enable administrative requests in this tab.</p>
        <OperatorAccess />
      </section>
    </main>
  );
}
