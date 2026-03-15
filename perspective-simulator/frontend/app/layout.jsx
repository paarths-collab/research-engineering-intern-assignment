export const metadata = { title: 'Perspective Simulator', description: 'Visual perspective interaction graph' };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, padding: 0, background: '#07070f' }}>{children}</body>
    </html>
  );
}
