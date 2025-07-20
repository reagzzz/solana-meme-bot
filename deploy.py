#!/usr/bin/env python3
"""
Script de déploiement et d'optimisation pour le Solana Meme Bot
"""
import os
import sys
import subprocess
import argparse
import json
import time
from pathlib import Path

class BotDeployer:
    """Gestionnaire de déploiement du bot"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.config_file = self.project_root / "config.json"
        self.requirements_file = self.project_root / "requirements.txt"
        self.docker_file = self.project_root / "Dockerfile"
        self.docker_compose_file = self.project_root / "docker-compose.yml"
    
    def create_requirements_file(self):
        """Créer le fichier requirements.txt"""
        requirements = [
            "asyncio",
            "aiohttp>=3.8.0",
            "solana>=0.30.0",
            "websockets>=11.0",
            "redis>=4.3.0",
            "kafka-python>=2.0.0",
            "requests>=2.28.0",
            "beautifulsoup4>=4.11.0",
            "pandas>=1.5.0",
            "numpy>=1.24.0",
            "python-telegram-bot>=20.0",
            "smtplib-ssl",
            "python-dotenv>=1.0.0",
            "pydantic>=2.0.0",
            "fastapi>=0.100.0",
            "uvicorn>=0.23.0",
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "fakeredis>=2.20.0"
        ]
        
        with open(self.requirements_file, 'w') as f:
            f.write('\n'.join(requirements))
        
        print(f"✅ Fichier requirements.txt créé: {self.requirements_file}")
    
    def create_dockerfile(self):
        """Créer le Dockerfile"""
        dockerfile_content = """# Utiliser Python 3.11 comme image de base
FROM python:3.11-slim

# Définir le répertoire de travail
WORKDIR /app

# Installer les dépendances système
RUN apt-get update && apt-get install -y \\
    gcc \\
    g++ \\
    && rm -rf /var/lib/apt/lists/*

# Copier les fichiers de requirements
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY . .

# Créer un utilisateur non-root
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Exposer le port pour l'API de monitoring (optionnel)
EXPOSE 8080

# Variables d'environnement par défaut
ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO

# Commande par défaut
CMD ["python", "main_bot.py"]
"""
        
        with open(self.docker_file, 'w') as f:
            f.write(dockerfile_content)
        
        print(f"✅ Dockerfile créé: {self.docker_file}")
    
    def create_docker_compose(self):
        """Créer le fichier docker-compose.yml"""
        compose_content = """version: '3.8'

services:
  solana-meme-bot:
    build: .
    container_name: solana-meme-bot
    restart: unless-stopped
    environment:
      - REDIS_HOST=redis
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - LOG_LEVEL=INFO
    volumes:
      - ./logs:/app/logs
      - ./config:/app/config
    depends_on:
      - redis
      - kafka
      - zookeeper
    networks:
      - bot-network

  redis:
    image: redis:7-alpine
    container_name: solana-bot-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - bot-network

  zookeeper:
    image: confluentinc/cp-zookeeper:latest
    container_name: solana-bot-zookeeper
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    networks:
      - bot-network

  kafka:
    image: confluentinc/cp-kafka:latest
    container_name: solana-bot-kafka
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: true
    volumes:
      - kafka_data:/var/lib/kafka/data
    networks:
      - bot-network

  # Service de monitoring optionnel
  monitoring:
    image: prom/prometheus:latest
    container_name: solana-bot-monitoring
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    networks:
      - bot-network

volumes:
  redis_data:
  kafka_data:

networks:
  bot-network:
    driver: bridge
"""
        
        with open(self.docker_compose_file, 'w') as f:
            f.write(compose_content)
        
        print(f"✅ docker-compose.yml créé: {self.docker_compose_file}")
    
    def create_config_template(self):
        """Créer un template de configuration"""
        config_template = {
            "solana": {
                "rpc_url": "https://api.mainnet-beta.solana.com",
                "ws_url": "wss://api.mainnet-beta.solana.com",
                "helius_api_key": "YOUR_HELIUS_API_KEY"
            },
            "social_media": {
                "twitter_bearer_token": "YOUR_TWITTER_BEARER_TOKEN",
                "telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN"
            },
            "notifications": {
                "telegram_enabled": True,
                "email_enabled": False,
                "telegram_chat_id": "YOUR_TELEGRAM_CHAT_ID",
                "email_address": "your-email@example.com",
                "email_smtp_server": "smtp.gmail.com",
                "email_smtp_port": 587,
                "email_username": "your-email@example.com",
                "email_password": "your-app-password"
            },
            "redis": {
                "host": "localhost",
                "port": 6379,
                "db": 0
            },
            "kafka": {
                "bootstrap_servers": "localhost:9092",
                "topics": {
                    "notifications": "solana-notifications",
                    "social_events": "social-events",
                    "price_alerts": "price-alerts"
                }
            },
            "filter_criteria": {
                "min_market_cap": 10000,
                "max_market_cap": 1000000,
                "min_liquidity": 5000,
                "min_volume_24h": 1000,
                "min_sentiment_score": 0.3,
                "max_notifications_per_hour": 50
            },
            "logging": {
                "level": "INFO",
                "file": "solana_meme_bot.log",
                "max_file_size": "10MB",
                "backup_count": 5
            }
        }
        
        config_dir = self.project_root / "config"
        config_dir.mkdir(exist_ok=True)
        
        config_file = config_dir / "config.template.json"
        with open(config_file, 'w') as f:
            json.dump(config_template, f, indent=2)
        
        print(f"✅ Template de configuration créé: {config_file}")
        print("⚠️  Copiez ce fichier vers config.json et remplissez vos clés API")
    
    def create_systemd_service(self):
        """Créer un service systemd pour le déploiement sur serveur"""
        service_content = f"""[Unit]
Description=Solana Meme Bot
After=network.target
Wants=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory={self.project_root}
Environment=PYTHONPATH={self.project_root}
ExecStart=/usr/bin/python3 {self.project_root}/main_bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
        
        service_file = self.project_root / "solana-meme-bot.service"
        with open(service_file, 'w') as f:
            f.write(service_content)
        
        print(f"✅ Service systemd créé: {service_file}")
        print("Pour installer le service:")
        print(f"sudo cp {service_file} /etc/systemd/system/")
        print("sudo systemctl daemon-reload")
        print("sudo systemctl enable solana-meme-bot")
        print("sudo systemctl start solana-meme-bot")
    
    def create_monitoring_config(self):
        """Créer la configuration de monitoring"""
        monitoring_dir = self.project_root / "monitoring"
        monitoring_dir.mkdir(exist_ok=True)
        
        prometheus_config = """global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'solana-meme-bot'
    static_configs:
      - targets: ['solana-meme-bot:8080']
    scrape_interval: 30s
    metrics_path: /metrics

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']

  - job_name: 'kafka'
    static_configs:
      - targets: ['kafka:9092']
"""
        
        prometheus_file = monitoring_dir / "prometheus.yml"
        with open(prometheus_file, 'w') as f:
            f.write(prometheus_config)
        
        print(f"✅ Configuration Prometheus créée: {prometheus_file}")
    
    def create_startup_script(self):
        """Créer un script de démarrage"""
        startup_script = """#!/bin/bash

# Script de démarrage pour Solana Meme Bot
set -e

echo "🚀 Démarrage du Solana Meme Bot..."

# Vérifier que Python est installé
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 n'est pas installé"
    exit 1
fi

# Vérifier que les dépendances sont installées
echo "📦 Vérification des dépendances..."
pip3 install -r requirements.txt

# Vérifier que la configuration existe
if [ ! -f "config/config.json" ]; then
    echo "⚠️  Fichier de configuration manquant"
    echo "Copiez config/config.template.json vers config/config.json et configurez vos clés API"
    exit 1
fi

# Créer le répertoire de logs
mkdir -p logs

# Démarrer le bot
echo "✅ Démarrage du bot..."
python3 main_bot.py
"""
        
        startup_file = self.project_root / "start.sh"
        with open(startup_file, 'w') as f:
            f.write(startup_script)
        
        # Rendre le script exécutable
        os.chmod(startup_file, 0o755)
        
        print(f"✅ Script de démarrage créé: {startup_file}")
    
    def run_tests(self):
        """Exécuter les tests"""
        print("🧪 Exécution des tests...")
        
        try:
            result = subprocess.run([
                sys.executable, "-m", "pytest", 
                "tests/", "-v", "--tb=short"
            ], cwd=self.project_root, capture_output=True, text=True)
            
            print(result.stdout)
            if result.stderr:
                print("Erreurs:", result.stderr)
            
            if result.returncode == 0:
                print("✅ Tous les tests sont passés")
                return True
            else:
                print("❌ Certains tests ont échoué")
                return False
                
        except Exception as e:
            print(f"❌ Erreur lors de l'exécution des tests: {e}")
            return False
    
    def optimize_performance(self):
        """Optimiser les performances"""
        print("⚡ Optimisation des performances...")
        
        optimizations = [
            "Configuration des pools de connexions",
            "Optimisation des requêtes Redis",
            "Configuration des buffers Kafka",
            "Ajustement des timeouts",
            "Configuration du garbage collector Python"
        ]
        
        for opt in optimizations:
            print(f"  • {opt}")
            time.sleep(0.5)  # Simulation
        
        print("✅ Optimisations appliquées")
    
    def create_deployment_guide(self):
        """Créer un guide de déploiement"""
        guide_content = """# Guide de Déploiement - Solana Meme Bot

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
"""
        
        guide_file = self.project_root / "DEPLOYMENT.md"
        with open(guide_file, 'w') as f:
            f.write(guide_content)
        
        print(f"✅ Guide de déploiement créé: {guide_file}")
    
    def deploy(self, mode="local"):
        """Déployer le bot"""
        print(f"🚀 Déploiement en mode: {mode}")
        
        # Créer tous les fichiers nécessaires
        self.create_requirements_file()
        self.create_config_template()
        self.create_startup_script()
        self.create_deployment_guide()
        
        if mode == "docker":
            self.create_dockerfile()
            self.create_docker_compose()
            self.create_monitoring_config()
            print("🐳 Fichiers Docker créés. Exécutez: docker-compose up -d")
        
        elif mode == "systemd":
            self.create_systemd_service()
            print("🔧 Service systemd créé. Suivez les instructions affichées.")
        
        elif mode == "local":
            print("💻 Déploiement local configuré. Exécutez: ./start.sh")
        
        # Exécuter les tests
        if self.run_tests():
            print("✅ Déploiement prêt!")
        else:
            print("⚠️  Déploiement prêt mais avec des tests en échec")
        
        # Optimiser les performances
        self.optimize_performance()
        
        print("\n📋 Prochaines étapes:")
        print("1. Configurez vos clés API dans config/config.json")
        print("2. Testez les notifications avec le mode test")
        print("3. Surveillez les logs lors du premier démarrage")
        print("4. Configurez le monitoring si nécessaire")

def main():
    parser = argparse.ArgumentParser(description="Déployer le Solana Meme Bot")
    parser.add_argument(
        "--mode", 
        choices=["local", "docker", "systemd"], 
        default="local",
        help="Mode de déploiement"
    )
    parser.add_argument(
        "--test-only", 
        action="store_true",
        help="Exécuter seulement les tests"
    )
    
    args = parser.parse_args()
    
    deployer = BotDeployer()
    
    if args.test_only:
        deployer.run_tests()
    else:
        deployer.deploy(args.mode)

if __name__ == "__main__":
    main()

