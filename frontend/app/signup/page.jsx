import AccountForm from '../../components/AccountForm';

export const metadata = { title: 'Create account | NarrativeSignal', robots: { index: false, follow: false } };

export default async function SignupPage({ searchParams }) {
  const params = await searchParams;
  return <AccountForm mode="signup" nextPath={params?.next} />;
}
