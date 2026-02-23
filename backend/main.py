from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json
from backend.agent import run_forensic_crew
# Import other chart endpoints from previous steps...

app = FastAPI()

class ChatRequest(BaseModel):
    query: str

@app.post("/chat")
def chat_agent(request: ChatRequest):
    print(f"received query: {request.query}")
    try:
        # 1. Run the CrewAI process
        raw_result = run_forensic_crew(request.query)
        
        # 2. Clean up the LLM output (It often adds markdown formatting)
        clean_json = raw_result.replace("```json", "").replace("```", "").strip()
        
        # 3. Parse to Dictionary
        response_dict = json.loads(clean_json)
        
        return response_dict
        
    except json.JSONDecodeError:
        # Fallback if LLM creates bad JSON
        return {
            "answer": raw_result,
            "follow_up": ["Try asking a simpler question", "Ask about specific dates"]
        }
    except Exception as e:
        print(f"Crew Error: {e}")
        return {
            "answer": "I encountered an internal error while coordinating the investigation team.",
            "follow_up": []
        }