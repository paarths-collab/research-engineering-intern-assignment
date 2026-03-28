import AppShell from "../components/AppShell";
import "../styles/globals.css";

export default function RootLayout({ children }) {
    return (
        <html lang="en">
            <body suppressHydrationWarning>
                <AppShell>{children}</AppShell>
            </body>
        </html>
    );
}
