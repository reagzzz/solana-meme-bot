# dashboard_api.py
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from pymongo import MongoClient
import asyncio
import json
import os

app = FastAPI()
mongo = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017/"))
db = mongo[os.getenv("MONGODB_DB_NAME", "solana_meme_bot")]

html = """
<!DOCTYPE html>
<html>
<head>
    <title>Solana Meme Bot Dashboard</title>
    <style>
        body { font-family: sans-serif; }
        #tokens { white-space: pre-wrap; }
    </style>
</head>
<body>
    <h1>📊 Solana Meme Bot - Dashboard</h1>
    <h2>🎯 Tokens détectés</h2>
    <div id="tokens">Chargement...</div>
    <script>
        const ws = new WebSocket("ws://localhost:8000/ws");
        ws.onmessage = function(event) {
            document.getElementById("tokens").textContent = event.data;
        };
    </script>
</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(html)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        tokens = list(db.tokens.find().sort("detected_at", -1).limit(10))
        data = "\n".join([f"{t['name']} - {t['symbol']} - Score: {t.get('score', 'N/A')}" for t in tokens])
        await websocket.send_text(data)
        await asyncio.sleep(5)
