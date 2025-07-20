# Guide de Déploiement - Solana Meme Bot

## Prérequis

### Système
- Python 3.11+
- Redis Server
- Apache Kafka (optionnel, pour la production)
- Docker et Docker Compose (pour le déploiement containerisé)

### Clés API Requises
- **Helius API Key**: Pour l'accès aux données Solana
- **Twitter Bearer Token**: Pour la surveillance Twitter
- **Telegram Bot Token**: Pour les notifications
- **Chat ID Telegram**: Pour recevoir les notifications

## Installation

### 1. Cloner et Configurer
```bash
git clone <repository-url>
cd solana-meme-bot
pip install -r requirements.txt
```

### 2. Configuration
```bash
cp config/config.template.json config/config.json
# Éditer config.json avec vos clés API
```

### 3. Déploiement Local
```bash
# Démarrage simple
./start.sh

# Ou avec Docker Compose
docker-compose up -d
```

### 4. Déploiement Production
```bash
# Installer le service systemd
sudo cp solana-meme-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable solana-meme-bot
sudo systemctl start solana-meme-bot
```

## Configuration des APIs

### Helius (Solana)
1. Créer un compte sur https://helius.xyz
2. Obtenir une clé API
3. Ajouter dans config.json: `"helius_api_key": "votre-clé"`

### Twitter
1. Créer une app sur https://developer.twitter.com
2. Obtenir le Bearer Token
3. Ajouter dans config.json: `"twitter_bearer_token": "votre-token"`

### Telegram
1. Créer un bot avec @BotFather
2. Obtenir le token du bot
3. Obtenir votre chat ID (envoyer un message au bot puis visiter https://api.telegram.org/bot<TOKEN>/getUpdates)
4. Ajouter dans config.json:
   ```json
   "telegram_bot_token": "votre-token",
   "telegram_chat_id": "votre-chat-id"
   ```

## Monitoring

### Logs
- Fichier: `solana_meme_bot.log`
- Niveau configurable dans config.json

### Métriques
- Prometheus: http://localhost:9090 (si activé)
- Statistiques intégrées dans les logs

### Santé du Système
Le bot surveille automatiquement:
- Connexions Redis/Kafka
- Taille des queues
- Taux d'erreur des APIs
- Performance des filtres

## Dépannage

### Problèmes Courants

1. **Erreur de connexion Redis**
   ```bash
   sudo systemctl start redis
   ```

2. **Clés API invalides**
   - Vérifier la configuration
   - Tester les clés manuellement

3. **Notifications non reçues**
   - Vérifier le chat ID Telegram
   - Vérifier les permissions du bot

4. **Performance lente**
   - Augmenter les ressources Redis
   - Ajuster les critères de filtrage
   - Vérifier la latence réseau

### Logs Utiles
```bash
# Logs du service
sudo journalctl -u solana-meme-bot -f

# Logs de l'application
tail -f solana_meme_bot.log

# Statut des services
sudo systemctl status solana-meme-bot
sudo systemctl status redis
```

## Sécurité

### Bonnes Pratiques
- Utiliser des variables d'environnement pour les clés sensibles
- Configurer un firewall approprié
- Mettre à jour régulièrement les dépendances
- Surveiller les logs pour les activités suspectes

### Variables d'Environnement
```bash
export HELIUS_API_KEY="votre-clé"
export TWITTER_BEARER_TOKEN="votre-token"
export TELEGRAM_BOT_TOKEN="votre-token"
```

## Maintenance

### Mises à Jour
```bash
git pull origin main
pip install -r requirements.txt
sudo systemctl restart solana-meme-bot
```

### Sauvegarde
- Configuration: `config/config.json`
- Logs: `logs/`
- Données Redis: selon la configuration

### Surveillance
- Vérifier les logs quotidiennement
- Surveiller les métriques de performance
- Tester les notifications périodiquement
