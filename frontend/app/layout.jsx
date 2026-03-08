"use client";

import { AnimatePresence, motion } from "framer-motion";
import { usePathname } from "next/navigation";
import "../styles/globals.css";

export default function RootLayout({ children }) {
    const pathname = usePathname();

    return (
        <html lang="en">
            <body>
                <AnimatePresence mode="wait">
                    <motion.div
                        key={pathname || "initial"}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.35 }}
                    >
                        {children}
                    </motion.div>
                </AnimatePresence>
            </body>
        </html>
    );
}
