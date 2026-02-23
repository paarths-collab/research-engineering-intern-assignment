import os
import json
from pathlib import Path
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI # Standard stable bridge
from langchain_groq import ChatGroq
from langchain.agents import Tool

# Import the plain functions from your tools file
from backend.crew_tools import execute_sql_func, search_vectors_func, analyze_bridges_func

# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Ensure CrewAI/LiteLLM can find the key
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "")

# ==============================================
# 1. SETUP HIGH-REASONING MODEL (Groq via OpenAI Bridge)
# ==============================================

high_reasoning_llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model="groq/llama-3.3-70b-versatile",
    temperature=0,
)


# ==============================================
# 2. WRAP TOOLS (Pydantic-Safe)
# ==============================================
sql_tool = Tool(
    name="execute_sql",
    func=execute_sql_func,
    description="Query statistics and post counts. Input: raw DuckDB SQL."
)

vector_tool = Tool(
    name="search_vectors",
    func=search_vectors_func,
    description="Search narratives and opinions. Input: search topic string."
)

bridge_tool = Tool(
    name="analyze_bridges",
    func=analyze_bridges_func,
    description="Find users crossing between subreddits. Input: two subreddit names."
)

# ==============================================
# 3. DEFINE SPECIALIST AGENTS
# ==============================================

quant_agent = Agent(
    role='Quantitative Analyst',
    goal='Provide accurate statistical data from the DuckDB database.',
    backstory="You are a SQL expert. You understand that the dataset spans July 2024 to Feb 2025.",
    tools=[sql_tool],
    llm=high_reasoning_llm,
    verbose=True,
    allow_delegation=False
)

narrative_agent = Agent(
    role='Narrative Researcher',
    goal='Analyze the meaning and framing of Reddit discussions.',
    backstory="You find hidden ideological frames and sentiment using semantic search.",
    tools=[vector_tool],
    llm=high_reasoning_llm,
    verbose=True,
    allow_delegation=False
)

forensic_agent = Agent(
    role='Forensic Detective',
    goal='Identify coordinated behavior and bridge users.',
    backstory="You find 'Super-Spreaders' and 131 suspicious copy-paste clusters.",
    tools=[bridge_tool, sql_tool],
    llm=high_reasoning_llm,
    verbose=True,
    allow_delegation=False
)

# ==============================================
# 4. THE ANALYSIS TASK & EXECUTION
# ==============================================

def run_forensic_crew(user_query: str):
    
    # This is the "Analysis Task" the Manager uses to orchestrate the crew
    # Define the Investigative Mission with strict constraints
    analysis_task = Task(
        description=f"""
        INVESTIGATIVE MISSION: "{user_query}"

        DATASET CONTEXT & CONSTRAINTS:
        - TIMEFRAME: July 23, 2024, to February 18, 2025.
        - VALID SUBREDDITS: [politics, Conservative, Anarchism, Liberal, Republican, 
          PoliticalDiscussion, socialism, worldpolitics, democrats, neoliberal].
        - NEVER use subreddits like 'news' or 'worldnews' — they are NOT in the dataset.
        - TEMPORAL LOGIC: Use YEAR 2025 for February, YEAR 2024 for November.
        - SQL RULES: Always use CAST(created_datetime AS DATE). Never use created_utc.

        RESEARCH DIRECTIVES:
        1. TOPIC OVERLAP: Check if multiple valid subreddits discuss the same event.
        2. ECHO CHAMBERS: Use 'analyze_bridges' to find users crossing communities.
        3. COORDINATED BEHAVIOR: Investigate 'duplicate_cluster_id'. If multiple posts 
           share the EXACT same timestamp (down to the second), report it as a 
           'Synchronized Bot Blast' — do NOT list every duplicate row, just summarize.
        4. MEDIA DIET: Identify external domains driving the narrative.

        FORENSIC PROCESS:
        1. PLAN: SQL for counts/duplicates. Vectors for narrative/meaning.
        2. EXECUTE: Max 2 tool retries per question. If a tool fails twice, move on.
        3. SYNTHESIZE: Conclude — Organic Viral News OR Coordinated Propaganda?

        FINAL OUTPUT MUST BE A JSON STRING:
        {{
            "answer": "3-4 sentences. Mention cluster IDs, subreddits, authors, and timing anomalies found.",
            "follow_up": ["Specific follow-up question 1", "Specific follow-up question 2"]
        }}
        """,
        expected_output="A clean JSON object.",
        agent=forensic_agent,
        max_iter=5  # Enough for 2-3 tool calls + retries, not enough to spiral
    )

    crew = Crew(
        agents=[quant_agent, narrative_agent, forensic_agent],
        tasks=[analysis_task],
        process=Process.sequential,
        verbose=True
    )

    from backend.rate_limit_handler import run_crew_sequentially
    
    try:
        result = run_crew_sequentially(crew)
        return str(result)
    except Exception as e:
        return '{"answer": "Sorry, could not complete the analysis due to repeated upstream API rate limits or errors.", "follow_up": []}'