// 'use client';
// import { motion } from 'framer-motion';
// import Link from 'next/link';
// import styles from './AmbrosiaPage.module.css';
// // import GlobeVisualization from './GlobeVisualization';
// import dynamic from "next/dynamic";

// const GlobeVisualization = dynamic(
//   () => import("./GlobeVisualization"),
//   { ssr: false }
// );
// export default function AmbrosiaPage() {
//   return (
//     <div className={styles.root}>

//       {/* NAVBAR */}
//       <nav className={styles.nav}>

//         <div className={styles.brand}>NarrativeSignal</div>

//         <ul className={styles.navLinks}>
//           <li><Link href="/overview">Overview</Link></li>
//           <li><Link href="/intelligence">Narrative Ecosystem</Link></li>
//           <li><Link href="/stream">Streamgraph</Link></li>
//           <li><Link href="/polar">Polar Analysis</Link></li>

//           {/* NEW ITEMS */}
//           <li><Link href="/globe">Globe</Link></li>
//           <li><Link href="/chatbot">Chatbot</Link></li>
//           <li><Link href="/datasets">Datasets</Link></li>
//         </ul>

//         <div className={styles.navRight}>
//           <a href="#">GitHub</a>
//           <a href="#">Docs</a>
//         </div>

//       </nav>



//       {/* GLOBE BACKGROUND */}
//       <div className={styles.globeContainer}>
//         <GlobeVisualization />
//         <div className={styles.signalLine}></div>
//       </div>
//       <motion.div
//         className={styles.platformLabel}
//         initial={{ opacity: 0 }}
//         animate={{ opacity: 0.6 }}
//         transition={{ delay: 0.2 }}
//       >
//         NARRATIVE ANALYSIS PLATFORM
//       </motion.div>
//       {/* HERO SECTION */}
//       <div className={styles.hero}>

//         <motion.div className={styles.platformLabel}>
//           NARRATIVE ANALYSIS PLATFORM
//         </motion.div>

//         <motion.h1 className={styles.title}>
//           NarrativeSignal
//         </motion.h1>
//         <motion.p
//           className={styles.tagline}
//           initial={{ opacity: 0, y: 20 }}
//           animate={{ opacity: 0.7, y: 0 }}
//           transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
//         >
//           Mapping how narratives move across networks.
//         </motion.p>

//         <motion.p
//           className={styles.description}
//           initial={{ opacity: 0, y: 20 }}
//           animate={{ opacity: 0.6, y: 0 }}
//           transition={{ duration: 0.8, delay: 0.4, ease: "easeOut" }}
//         >
//           NarrativeSignal is a research visualization interface for exploring how information spreads across communities using network graphs, temporal analysis, and polarization metrics.
//         </motion.p>

//         <motion.div
//           className={styles.actions}
//           initial={{ opacity: 0, y: 20 }}
//           animate={{ opacity: 1, y: 0 }}
//           transition={{ duration: 0.8, delay: 0.6, ease: "easeOut" }}
//         >
//           <button className={styles.btnPrimary}>Launch Dashboard</button>
//           <button className={styles.btnSecondary}>Explore Visualizations</button>
//         </motion.div>
//       </div>

//       <div className={styles.liveMetrics}>
//         <div style={{ color: '#FFB800', marginBottom: '8px', fontSize: '11px', letterSpacing: '1px' }}>LIVE SIGNALS</div>
//         <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}><span>Narratives tracked</span> <span>124</span></div>
//         <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}><span>Communities analyzed</span> <span>31</span></div>
//         <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}><span>Bridge actors detected</span> <span>72</span></div>
//         <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Active signals</span> <span style={{ color: '#FFB800' }}>9</span></div>
//       </div>
//     </div>
//   );
// }

'use client';
import { motion } from 'framer-motion';
import Link from 'next/link';
import styles from './AmbrosiaPage.module.css';
import ParticlesBackground from './ParticlesBackground';
// import GlobeVisualization from './GlobeVisualization';
import dynamic from "next/dynamic";

const GlobeVisualization = dynamic(
  () => import("./GlobeVisualization"),
  { ssr: false }
);
export default function AmbrosiaPage() {
  return (
    <div className={styles.root}>
      <ParticlesBackground />

      {/* NAVBAR */}
      <nav className={styles.nav}>

        <div className={styles.brand}>NarrativeSignal</div>

        <ul className={styles.navLinks}>
          <li><Link href="/overview">Overview</Link></li>
          <li><Link href="/network">Network Graph</Link></li>
          <li><Link href="/stream">Streamgraph</Link></li>
          <li><Link href="/polar">Polar Analysis</Link></li>

          {/* NEW ITEMS */}
          <li><Link href="/globe">Globe</Link></li>
          <li><Link href="/perspective">Perspective</Link></li>
          <li><Link href="/chatbot">Chatbot</Link></li>
        </ul>

        <div className={styles.navRight}>
          <a href="#">GitHub</a>
          <a href="#">Docs</a>
        </div>

      </nav>



      {/* GLOBE BACKGROUND */}
      <div className={styles.globeContainer}>
        <GlobeVisualization />
        <div className={styles.signalLine}></div>
      </div>
      <motion.div
        className={styles.platformLabel}
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.6 }}
        transition={{ delay: 0.2 }}
      >
        NARRATIVE ANALYSIS PLATFORM
      </motion.div>
      {/* HERO SECTION */}
      <div className={styles.hero}>

        <motion.div className={styles.platformLabel}>
          NARRATIVE ANALYSIS PLATFORM
        </motion.div>

        <motion.h1 className={styles.title}>
          NarrativeSignal
        </motion.h1>
        <motion.p
          className={styles.tagline}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 0.7, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
        >
          Mapping how narratives move across networks.
        </motion.p>

        <motion.p
          className={styles.description}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 0.6, y: 0 }}
          transition={{ duration: 0.8, delay: 0.4, ease: "easeOut" }}
        >
          NarrativeSignal is a research visualization interface for exploring how information spreads across communities using network graphs, temporal analysis, and polarization metrics.
        </motion.p>

        <motion.div
          className={styles.actions}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.6, ease: "easeOut" }}
        >
          <Link href="/overview" className={styles.btnPrimary}>Overview Dashboard</Link>
          <Link href="/intelligence" className={styles.btnSecondary}>Explore Visualizations</Link>
        </motion.div>
      </div>

      <div className={styles.liveMetrics}>
        <div style={{ color: '#FFB800', marginBottom: '8px', fontSize: '11px', letterSpacing: '1px' }}>LIVE SIGNALS</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}><span>Narratives tracked</span> <span>124</span></div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}><span>Communities analyzed</span> <span>31</span></div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}><span>Bridge actors detected</span> <span>72</span></div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Active signals</span> <span style={{ color: '#FFB800' }}>9</span></div>
      </div>
    </div>
  );
}