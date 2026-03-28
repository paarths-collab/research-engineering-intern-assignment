# 📄 prompt.md

## Narrative Intelligence — Prompt Set (based on `data.jsonl`)

---

### 1. First, understand what data I actually have

```
I have a data.jsonl file. Before doing any analysis, I want to understand what is actually present instead of assuming.

Explain:
- what kind of fields typically exist in such datasets
- what each field can tell me (text, author, subreddit, timestamp, domain, etc.)
- what kind of signals I can extract from them

Then write a small Python snippet to:
- load the file
- print available keys
- show a few sample rows
```

---

### 2. Verify assumptions about the dataset

```
I want to confirm whether fields like text, author, subreddit, timestamp, and domain actually exist.

Write logic (not just explanation) to:
- check if these fields are present
- handle cases where names differ
- suggest closest matches if exact names are missing

Keep it simple and practical.
```

---

### 3. Get a quick feel of the data

```
Given the dataset, what are the first things you would check to understand it?

Answer briefly, then write code to:
- count unique authors
- count subreddits
- show most active ones

Focus on building intuition about the data.
```

---

### 4. Check if the text is usable

```
Before extracting narratives, I want to understand how clean the text is.

Explain what issues might exist in raw Reddit text.

Then write code to:
- check empty/null posts
- measure average length
- print a few cleaned samples
```

---

### 5. Validate timestamps before using them

```
Explain why timestamp validation is important in narrative analysis.

Then write code to:
- inspect timestamp format
- convert to datetime
- detect invalid values
- show time range of the dataset
```

---

### 6. Extract narratives from posts

```
I want to identify underlying narratives, not just topics.

Explain briefly how clustering helps here.

Then write code to:
- preprocess text
- apply TF-IDF
- cluster posts
- output top keywords and sample posts per cluster
```

---

### 7. See how narratives spread across subreddits

```
Explain what it means for a narrative to "spread".

Then write logic/code to:
- map each narrative cluster to subreddits
- compare how widely each narrative appears

Focus on interpretation, not just raw output.
```

---

### 8. Analyze author behavior

```
What patterns would indicate that an author is influential or acting as a bridge?

Answer briefly.

Then write code to:
- find authors active in multiple subreddits
- count posts per author
- flag unusual behavior patterns
```

---

### 9. Look for unusual activity spikes

```
Explain why spikes in activity matter in narrative analysis.

Then write code to:
- group posts over time
- detect sudden increases
- link spikes to possible narratives or events
```

---

### 10. Analyze domains and sources

```
Explain how domains can influence narratives.

Then write code to:
- find most shared domains
- check if certain domains dominate specific subreddits

If domain field is missing, suggest how to extract it from text.
```
