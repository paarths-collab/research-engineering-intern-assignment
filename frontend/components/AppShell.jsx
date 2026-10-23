"use client";

import { AnimatePresence, motion } from "framer-motion";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";
import OperatorAccess from "./OperatorAccess";

export default function AppShell({ children }) {
  const pathname = usePathname();

  return (
    <>
      <Sidebar />
      <OperatorAccess />
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
    </>
  );
}
