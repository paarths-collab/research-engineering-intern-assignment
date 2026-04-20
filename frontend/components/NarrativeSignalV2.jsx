'use client';
import Image from 'next/image';
import Link from 'next/link';
import { motion } from 'framer-motion';
import dynamic from 'next/dynamic';
import styles from './NarrativeSignalV2.module.css';

const HeroGlobe = dynamic(() => import('./HeroGlobe'), { ssr: false, loading: () => null });

const NAV_LINKS = [
  { label: 'Overview', href: '/overview', active: true },
  { label: 'Globe', href: '/globe' },
  { label: 'Network', href: '/network' },
  { label: 'Streamgraph', href: '/stream' },
  { label: 'Polar Analysis', href: '/polar' },
  { label: 'Perspective', href: '/perspective' },
  { label: 'Intelligence', href: '/chatbot' },
];

const ease = [0.22, 1, 0.36, 1];

export default function NarrativeSignalV2() {
  return (
    <>
    <div className={styles.heroSection}>
      {/* NEBULA BACKGROUND */}
      <motion.div className={styles.bgLayer}>
        <Image
          src="/hero-bg.png"
          alt="Cosmic nebula background"
          fill
          priority
          quality={95}
          className={styles.bgImage}
        />
      </motion.div>

      {/* NAVBAR */}
      <nav className={styles.nav}>
        <Link href="/" className={styles.brandBlock}>
          <span className={styles.brandName}>NarrativeSignal</span>
          <span className={styles.brandSub}>Intelligence Platform</span>
        </Link>

        <ul className={styles.navLinks}>
          {NAV_LINKS.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className={link.active ? styles.navActive : undefined}
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>

        <div className={styles.navRight}>
          <Link href="/overview" className={styles.navBtn}>
            Dashboard
          </Link>
          <div className={styles.navAvatar}>N</div>
        </div>
      </nav>

      {/* HERO TITLE */}
      <motion.div className={styles.heroContent}>
        <motion.h1
          className={styles.title}
          initial={{ opacity: 0, y: -18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, delay: 0.2, ease }}
        >
          NARRATIVESIGNAL
        </motion.h1>

        <motion.div 
          className={styles.titleLine}
          initial={{ scaleX: 0, opacity: 0 }}
          animate={{ scaleX: 1, opacity: 1 }}
          transition={{ duration: 1.2, delay: 0.8, ease }}
        />

        <motion.p
          className={styles.tagline}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1, delay: 0.55, ease }}
        >
          Intelligence, Mapped at the Scale of Worlds
        </motion.p>
      </motion.div>

      {/* CENTERED GLOBE */}
      <motion.div
        className={styles.globeWrap}
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.4, delay: 0.3, ease }}
      >
        <div>
          <HeroGlobe />
        </div>
      </motion.div>

      {/* BOTTOM HUD */}
      <div className={styles.bottomLeft}>
        <div className={styles.chapterLabel}>Chapter 01</div>
        <div className={styles.chapterTitle}>The Awakening</div>
      </div>
    </div>
    </>
  );
}
