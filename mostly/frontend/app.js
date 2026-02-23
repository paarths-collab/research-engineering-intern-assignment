const API_BASE = "http://127.0.0.1:8000/api/v1";

// ============================================
// 1. TIMELINE STREAMGRAPH
// ============================================
async function loadTimeline() {
    const data = await fetch(`${API_BASE}/viz/timeline`).then(res => res.json());

    // Group by Subreddit
    const subs = [...new Set(data.map(d => d.subreddit))];
    const traces = subs.map(sub => {
        const subData = data.filter(d => d.subreddit === sub);
        return {
            x: subData.map(d => d.date),
            y: subData.map(d => d.post_count),
            name: `r/${sub}`,
            stackgroup: 'one', // Creates the Streamgraph effect
            mode: 'none'
        };
    });

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#94a3b8' },
        margin: { t: 10, l: 30, r: 10, b: 30 },
        xaxis: { gridcolor: '#334155' },
        yaxis: { gridcolor: '#334155' },
        legend: { orientation: 'h', y: 1.1 }
    };

    Plotly.newPlot('timelineChart', traces, layout);
}

// 2. CONTEXT AGENT (The Scraper)
async function analyzeContext(date) {
    const box = document.getElementById('contextBox');
    box.classList.remove('hidden');
    box.innerHTML = "🕵️ Agent is analyzing global news archives for this date...";

    try {
        const res = await fetch(`${API_BASE}/context?date=${date}`);
        const data = await res.json();
        box.innerHTML = `<strong>📅 EVENT DETECTED:</strong> ${data.context}`;
    } catch (e) {
        box.innerHTML = "❌ Error connecting to Intelligence Agent.";
    }
}

// ============================================
// 3. SANKEY DIAGRAM (Media Flow)
// ============================================
async function loadSankey() {
    const data = await fetch(`${API_BASE}/viz/sankey`).then(res => res.json());

    const allNodes = [...new Set([...data.map(d => d.subreddit), ...data.map(d => d.domain)])];
    const nodeMap = {};
    allNodes.forEach((n, i) => nodeMap[n] = i);

    // Color logic: Blue for Subs, Orange for Domains
    const colors = allNodes.map(n => n.includes('.') ? '#f59e0b' : '#06b6d4');

    const trace = {
        type: "sankey",
        node: {
            pad: 15, thickness: 20,
            line: { color: "black", width: 0.5 },
            label: allNodes,
            color: colors
        },
        link: {
            source: data.map(d => nodeMap[d.subreddit]),
            target: data.map(d => nodeMap[d.domain]),
            value: data.map(d => d.value),
            color: "rgba(255,255,255,0.1)"
        }
    };

    Plotly.newPlot('sankeyChart', [trace], {
        paper_bgcolor: 'rgba(0,0,0,0)', font: { color: '#94a3b8' },
        margin: { t: 20, l: 20, r: 20, b: 20 }
    });
}

// ============================================
// 4. PROPAGANDA FORENSICS (Table + Cascade)
// ============================================
async function loadPropaganda() {
    const data = await fetch(`${API_BASE}/viz/propaganda`).then(res => res.json());
    const tbody = document.getElementById('propagandaTable');

    data.forEach(row => {
        const tr = document.createElement('tr');
        tr.className = "prop-row border-b border-slate-800 text-slate-300";
        tr.innerHTML = `
            <td class="p-2 text-red-400 font-bold">#${row.id}</td>
            <td class="p-2 truncate max-w-[150px]" title="${row.headline}">${row.headline}</td>
            <td class="p-2 text-right font-mono">${row.total_posts}</td>
        `;
        // Click to load cascade
        tr.onclick = () => loadCascade(row.id, row.headline);
        tbody.appendChild(tr);
    });
}

async function loadCascade(clusterId, headline) {
    const data = await fetch(`${API_BASE}/viz/cascade/${clusterId}`).then(res => res.json());

    // Visualize as a Scatter Plot (Time vs Subreddit)
    const trace = {
        x: data.map(d => d.created_datetime),
        y: data.map(d => d.subreddit),
        mode: 'markers',
        marker: { size: 10, color: '#f87171' }, // Red dots
        text: data.map(d => `User: ${d.author}`),
        type: 'scatter'
    };

    const layout = {
        title: { text: `Propagation: "${headline.substring(0, 20)}..."`, font: { size: 12, color: '#fff' } },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#94a3b8' },
        xaxis: { title: 'Time of Post', gridcolor: '#334155' },
        yaxis: { title: 'Target Subreddit', gridcolor: '#334155' },
        margin: { t: 30, l: 100, r: 20, b: 40 }
    };

    Plotly.newPlot('cascadeChart', [trace], layout);
}

// ============================================
// 5. CHAT AGENT
// ============================================
async function sendChat() {
    const input = document.getElementById('chatInput');
    const history = document.getElementById('chatHistory');
    const q = input.value;
    if (!q) return;

    // User Msg
    history.innerHTML += `<div class="chat-msg user">${q}</div>`;
    input.value = "";
    history.scrollTop = history.scrollHeight;

    // Show Loading
    const loadingId = "loading-" + Date.now();
    history.innerHTML += `<div id="${loadingId}" class="chat-msg agent animate-pulse">Analyzing...</div>`;

    try {
        const res = await fetch(`http://127.0.0.1:8000/api/chat`, { // Fixed path to /api/chat instead of versioned base
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: q })
        });
        const json = await res.json();

        // Remove loading
        document.getElementById(loadingId).remove();

        // Agent Msg
        let html = `<div class="chat-msg agent">
            <div class="font-bold text-cyan-400 mb-1">AGENT REPORT</div>
            ${json.answer}
        </div>`;

        // Follow-ups
        if (json.follow_up) {
            html += `<div class="mt-2 text-right">`;
            json.follow_up.forEach(tip => {
                html += `<button onclick="document.getElementById('chatInput').value='${tip}'; sendChat()" class="text-[10px] bg-slate-700 text-cyan-200 px-2 py-1 rounded ml-2 hover:bg-slate-600 border border-slate-600">↳ ${tip.substring(0, 30)}...</button>`;
            });
            html += `</div>`;
        }

        history.innerHTML += html;
        history.scrollTop = history.scrollHeight;

    } catch (e) {
        document.getElementById(loadingId).innerText = "Error: Agent Offline.";
    }
}

// Start
loadTimeline();
loadSankey();
loadPropaganda();
