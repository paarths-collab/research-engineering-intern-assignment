import useGraphStore from '../store/graphStore';
import { simulateGraph } from '../services/perspectiveAPI';

const PRESET_PERSONAS = [
  { label: 'Tech Optimist', traits: ['pro-innovation', 'liberal', 'globalist'], ideology_vector: [0.8, 0.2, 0.9, 0.1] },
  { label: 'Traditionalist', traits: ['conservative', 'nationalist', 'anti-tech'], ideology_vector: [0.1, 0.9, 0.1, 0.8] },
  { label: 'Progressive', traits: ['social-justice', 'green', 'equality'], ideology_vector: [0.7, 0.3, 0.8, 0.2] },
  { label: 'Libertarian', traits: ['free-market', 'anti-regulation', 'individual'], ideology_vector: [0.6, 0.5, 0.3, 0.6] },
];

const PRESET_NEWS = [
  { label: 'AI Regulation Bill', description: 'Government proposes mandatory safety rules for all AI systems.' },
  { label: 'Climate Emergency Act', description: 'New legislation mandates net-zero emissions by 2030.' },
  { label: 'Universal Basic Income', description: 'Pilot program to give every citizen $1,000/month.' },
  { label: 'Crypto Tax Reform', description: 'Digital assets to be taxed as regular income.' },
];

export default function PerspectiveToolbar({ onAddPersona, onAddNews }) {
  const { nodes, edges, resetGraph, isSimulating, setSimulating, applySimulationResult } = useGraphStore();

  const handleSimulate = async () => {
    const personas = nodes.filter(n => n.type === 'persona');
    const news = nodes.filter(n => n.type === 'news');
    if (personas.length < 2 || news.length < 1) {
      alert('Add at least 2 persona nodes and 1 news node, then connect them.');
      return;
    }
    setSimulating(true);
    try {
      const result = await simulateGraph(nodes, edges);
      applySimulationResult(result);
    } catch (e) {
      console.error(e);
      alert('Simulation failed. Make sure the backend is running.');
      setSimulating(false);
    }
  };

  return (
    <div className="perspective-toolbar">
      <div className="toolbar-brand">
        <span className="brand-dot" />
        <span className="brand-name">Perspective</span>
      </div>

      <div className="toolbar-section">
        <div className="toolbar-label">Add Node</div>
        <div className="toolbar-buttons">
          <div className="preset-group">
            <button className="toolbar-btn persona-btn" onClick={() => onAddPersona()}>
              + Persona
            </button>
            <div className="preset-dropdown">
              {PRESET_PERSONAS.map((p, i) => (
                <button key={i} className="preset-item" onClick={() => onAddPersona(p)}>{p.label}</button>
              ))}
            </div>
          </div>
          <div className="preset-group">
            <button className="toolbar-btn news-btn" onClick={() => onAddNews()}>
              + News
            </button>
            <div className="preset-dropdown">
              {PRESET_NEWS.map((n, i) => (
                <button key={i} className="preset-item" onClick={() => onAddNews(n)}>{n.label}</button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="toolbar-divider" />

      <div className="toolbar-section">
        <button
          className={`simulate-btn ${isSimulating ? 'simulating' : ''}`}
          onClick={handleSimulate}
          disabled={isSimulating}
        >
          {isSimulating ? (
            <><span className="spinner" /> Analyzing...</>
          ) : (
            <><span className="play-icon">▶</span> Simulate</>
          )}
        </button>
        <button className="reset-btn" onClick={resetGraph}>Reset</button>
      </div>

      <div className="toolbar-stats">
        <span>{nodes.filter(n=>n.type==='persona').length} personas</span>
        <span>{nodes.filter(n=>n.type==='news').length} news</span>
        <span>{edges.length} edges</span>
      </div>
    </div>
  );
}
