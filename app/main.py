import uvicorn
from fastapi import FastAPI, Form
from agent_controller import agent_manager 

app = FastAPI()

@app.post("/chat")
async def chat_endpoint(
    text: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    user_id: str = Form(...) 
):
    print(f"📩 User {user_id} says: {text}")
    
    # 2. USE THE MANAGER: Call process_message on the global instance
    response_text = await agent_manager.process_message(user_id, text, latitude, longitude)
    
    print(f"🤖 Reply to {user_id}: {response_text}")
    
    return {
        "response": response_text
    }

if __name__ == "__main__":
    print("🚀 Starting Server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)