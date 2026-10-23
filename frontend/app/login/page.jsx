import AccountForm from '../../components/AccountForm';

export const metadata = { title: 'Sign in | NarrativeSignal', robots: { index: false, follow: false } };

export default async function LoginPage({ searchParams }) {
  const params = await searchParams;
  return <AccountForm mode="login" nextPath={params?.next} />;
}
