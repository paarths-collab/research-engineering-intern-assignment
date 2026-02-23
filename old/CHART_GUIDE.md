# 📊 CHART INTERPRETATION GUIDE

## Understanding the 4 Analysis Charts

---

## Chart 1: Activity Shock
**Type:** Grouped Bar Chart (Daily Volume)

### What You See
```
Posts
 │
400 │     ████
    │     ████
300 │     ████     ████
    │     ████     ████
200 │ ████████ ████████ ████
    │ ████████ ████████ ████
100 │ ████████ ████████ ████
    │ ████████ ████████ ████
    └─────────────────────────
      Mon Tue Wed Thu Fri Sat Sun
         BEFORE   │   AFTER
                EVENT
```

### How to Read
- **Blue bars** = Before event
- **Purple bars** = After event  
- **Height** = Number of posts per day

### What to Look For
- ✅ **Spike** = Major increase → Event triggered activity
- ⚠️ **Drop** = Decrease → Community quieted down
- ➡️ **Stable** = Similar heights → No volume change

### Metric Shown
- **Before Rate**: 156 posts/day
- **After Rate**: 354 posts/day
- **Change**: +127% ← THIS IS THE KEY NUMBER

---

## Chart 2: Discussion Intensity
**Type:** Distribution Histogram (Comments per Post)

### What You See
```
Posts
 │
 60│     ████
    │     ████
 40│     ████ ████
    │ ████████ ████
 20│ ████████ ████████ ████
    │ ████████ ████████ ████████
    └──────────────────────────────
      0-5  5-10 10-25 25-50 50+
           Comment Ranges
      
      Blue = Before  
      Purple = After
```

### How to Read
- **X-axis** = Comment ranges (0-5, 5-10, etc.)
- **Y-axis** = Number of posts in each range
- **Shift right** = More posts with high comments

### What to Look For
- ✅ **Right shift** = More debate/engagement
- ⚠️ **Left shift** = Less discussion
- ➡️ **Similar** = Stable engagement

### Metric Shown
- **Before Median**: 12 comments/post
- **After Median**: 17 comments/post
- **Change**: +43% ← More people debating

---

## Chart 3: Attention Redistribution
**Type:** Lorenz Curve (Cumulative Distribution)

### What You See
```
% of Total Score
 │
100│              ╱─────
    │            ╱
 75│          ╱
    │        ╱
 50│      ╱  After (more curved)
    │    ╱   
 25│  ╱    Before (less curved)
    │╱
  0└────────────────────
   0  25  50  75  100
   % of Posts (ranked)
   
   Diagonal line = Perfect equality
```

### How to Read
- **Diagonal line** = Perfect equality (all posts equal attention)
- **Curved line** = Actual distribution
- **More curved** = More inequality (few posts dominate)

### What to Look For
- ✅ **Curve moves away from diagonal** = Attention concentrated
- ⚠️ **Curve moves toward diagonal** = More distributed
- ➡️ **Similar curve** = Stable distribution

### Metric Shown
- **Before Gini**: 0.67 (moderate inequality)
- **After Gini**: 0.75 (high inequality)
- **Δ Gini**: +0.08 ← Attention concentrated on viral posts

### Understanding Gini
- **0.0** = Everyone gets equal attention
- **0.5** = Moderate inequality
- **1.0** = One post gets ALL attention

---

## Chart 4: Topic Shift
**Type:** Keyword Tables (Before vs After)

### What You See
```
BEFORE Keywords          AFTER Keywords
─────────────────        ─────────────────
policy        145        trump         289
debate        132        election      267
congress      98         victory       201
senate        87         results       178
bill          76         win           156
```

### How to Read
- **Left table** = Most common words BEFORE event
- **Right table** = Most common words AFTER event
- **Numbers** = Frequency of each word

### What to Look For
- ✅ **Different words** = Topic shifted significantly
- ⚠️ **Similar words** = Topic stable
- ➡️ **Some overlap** = Related but evolved

### Metric Shown
- **Cosine Similarity**: 0.58 (somewhat related)
- **Cosine Distance**: 0.42 (significant shift)

### Understanding Cosine Distance
- **0.0** = Identical topics
- **0.3** = Moderate shift
- **0.5** = Major shift
- **1.0** = Completely different

---

## Real Example: U.S. Presidential Election

### Event: Nov 5, 2024

| Dimension | Before | After | Change | Interpretation |
|-----------|--------|-------|--------|----------------|
| **Activity** | 156/day | 354/day | +127% | ✅ Major spike |
| **Discussion** | 12 comments | 17 comments | +43% | ✅ More debate |
| **Attention** | 0.67 Gini | 0.75 Gini | +0.08 | ⚠️ Concentrated |
| **Topics** | policy, debate | trump, victory | 0.42 | ✅ Shifted |

### Combined Interpretation

**What happened:** 
The U.S. Presidential Election caused a **major structural reorganization** of the Reddit political communities:

1. **Volume doubled** - people showed up
2. **Engagement deepened** - not just links, actual debate
3. **Attention concentrated** - few viral posts dominated
4. **Topics shifted** - from policy discussion to election results

**Significance:**
This was a **genuine shock** to the system, not just noise. The community fundamentally reorganized around this event.

---

## Pattern Recognition

### Pattern 1: Major Event Response
- Activity: **+100%+**
- Discussion: **+40%+**
- Gini: **+0.10+**
- Topic: **0.4+ distance**

→ **Community completely reorganized**

### Pattern 2: Moderate Event
- Activity: **+20-50%**
- Discussion: **+10-30%**
- Gini: **±0.05**
- Topic: **0.2-0.4 distance**

→ **Acknowledged but didn't dominate**

### Pattern 3: Non-Event
- Activity: **±10%**
- Discussion: **±10%**
- Gini: **±0.03**
- Topic: **<0.2 distance**

→ **Community largely unaffected**

---

## Interactive Features

All charts are **interactive** with Plotly.js:

- **Hover** → See exact values
- **Zoom** → Click and drag to zoom
- **Pan** → Shift + drag to move
- **Reset** → Double-click to reset view
- **Legend** → Click to toggle series

---

## Chart Customization

Want different views? Edit the chart configurations in `index.html`:

### Change Colors
```javascript
marker: { color: '#667eea' }  // Change to your color
```

### Adjust Layout
```javascript
layout: {
    height: 400,  // Taller chart
    title: 'Your Title'
}
```

### Add Annotations
```javascript
annotations: [{
    x: 'Nov 5',
    y: 354,
    text: 'Election Day Spike',
    showarrow: true
}]
```

---

## Exporting Charts

**As Image:**
- Hover over chart → Camera icon → Download plot as PNG

**As Data:**
- Results are in JSON format
- Can export to CSV/Excel for further analysis

---

## Key Takeaway

These 4 charts work **together** to tell a complete story:

1. **Activity** = Did people care?
2. **Discussion** = Did they engage?
3. **Attention** = Where did focus go?
4. **Topics** = What did they talk about?

This isn't just visualization - it's **quantitative social science**.
