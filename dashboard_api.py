from fastapi.responses import HTMLResponse
from pymongo import MongoClient
from fastapi import FastAPI
from bson.json_util import dumps
import json
import os

app = FastAPI()

# Connexion MongoDB
client = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017/"))
db = client[os.getenv("MONGODB_DB_NAME", "solana_meme_bot")]
collection = db["detected_tokens"]

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <html>
        <head>
            <title>Solana Meme Bot - Dashboard</title>
            <style>
                table { border-collapse: collapse; width: 100%; margin-top: 20px; }
                th, td { border: 1px solid #ccc; padding: 8px; text-align: center; }
                th { background-color: #f2f2f2; }
            </style>
        </head>
        <body>
            <h1>📊 Solana Meme Bot - Dashboard</h1>
            <h2>🎯 Tokens détectés</h2>
            <div id="table">Chargement...</div>

            <script>
                fetch("/tokens")
                    .then(response => response.json())
                    .then(data => {
                        let html = '<table><tr><th>Nom</th><th>Symbole</th><th>Market Cap ($)</th><th>Volume 24h</th><th>Date</th></tr>';
                        data.forEach(token => {
                            html += `<tr>
                                <td>${token.name}</td>
                                <td>${token.symbol}</td>
                                <td>${token.market_cap}</td>
                                <td>${token.volume_24h}</td>
                                <td>${new Date(token.created_at).toLocaleString()}</td>
                            </tr>`;
                        });
                        html += '</table>';
                        document.getElementById("table").innerHTML = html;
                    })
                    .catch(err => {
                        document.getElementById("table").innerText = "Erreur de chargement des données.";
                        console.error(err);
                    });
            </script>
        </body>
    </html>
    """

@app.get("/tokens")
async def get_tokens():
    tokens = list(collection.find().sort("created_at", -1).limit(50))
    for token in tokens:
        token["_id"] = str(token["_id"])  # Convertir ObjectId en str
    return tokens
