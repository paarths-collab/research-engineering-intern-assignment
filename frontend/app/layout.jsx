"use client";

import { AnimatePresence, motion } from "framer-motion";
import { usePathname } from "next/navigation";
import Sidebar from "../components/Sidebar";
import "../styles/globals.css";

export default function RootLayout({ children }) {
    const pathname = usePathname();

    return (
        <html lang="en">
            <body>
                <Sidebar />
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
