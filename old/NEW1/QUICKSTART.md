# 🚀 QUICKSTART GUIDE

## Get Running in 3 Steps

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Start Backend
```bash
python main.py
```

Server starts at `http://localhost:8000`

### Step 3: Open Frontend
Open `index.html` in your browser

---

## Usage

1. **Upload Data** → Click "Choose JSONL File" → Select `data.jsonl`
2. **Select Event** → Click any event card (e.g., "U.S. Presidential Election")
3. **Analyze** → Click "Analyze Event"
4. **View Results** → See 4 interactive charts

---

## What You Get

### 4 Analysis Dimensions

| Metric | What It Measures | Chart Type |
|--------|-----------------|------------|
| **Activity Shock** | Did posting volume spike? | Daily histogram |
| **Discussion Intensity** | Did people debate more? | Comment distribution |
| **Attention Redistribution** | Did few posts go viral? | Lorenz curve |
| **Topic Shift** | Did topics change? | Keyword comparison |

---

## File Structure

```
shock-response-analyzer/
├── main.py              # FastAPI backend
├── index.html           # Frontend UI
├── requirements.txt     # Python dependencies
├── README.md           # Full documentation
├── start.sh            # Quick start script
├── test_api.py         # API testing
├── metrics_guide.py    # Metrics explanation
└── QUICKSTART.md       # This file
```

---

## Example Output

**U.S. Presidential Election (Nov 5, 2024)**

- ✅ **Activity**: +127% spike (156 → 354 posts/day)
- ✅ **Discussion**: +43% increase (12 → 17 median comments)
- ⚠️ **Attention**: +0.08 Gini (concentrated on few viral posts)
- ✅ **Topics**: 0.42 distance (significant shift from "policy" to "results")

**Interpretation:** Major community reorganization - people showed up, debated intensely, but attention concentrated on few dominant posts.

---

## Troubleshooting

**Can't connect to API?**
→ Make sure `python main.py` is running

**CORS errors?**
→ Backend must be on port 8000
→ Open index.html directly (not from file:///)

**No data?**
→ Check JSONL format is correct
→ Verify `created_utc` field exists

---

## Learn More

- **Full Documentation**: See `README.md`
- **Metrics Explained**: Run `python metrics_guide.py`
- **API Testing**: Run `python test_api.py`

---

## Key Insight

This system doesn't just measure sentiment (unreliable).

It measures **structural reorganization** (quantifiable):
- How behavior changed
- How attention shifted  
- How topics evolved
- How engagement deepened

This is the difference between a dashboard and a **measurement engine**.
