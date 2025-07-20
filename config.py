"""
Configuration du Bot de Trading Meme Coins Solana
"""
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

class Config:
    # Configuration Solana
    SOLANA_RPC_URL = os.getenv('SOLANA_RPC_URL', 'https://api.mainnet-beta.solana.com')
    SOLANA_WS_URL = os.getenv('SOLANA_WS_URL', 'wss://api.mainnet-beta.solana.com')
    
    # Configuration Redis (Cache)
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))
    
    # Configuration MongoDB
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    MONGODB_DB_NAME = os.getenv('MONGODB_DB_NAME', 'solana_meme_bot')
    
    # Configuration Kafka
    KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    KAFKA_TOPICS = {
        'new_tokens': 'solana_new_tokens',
        'market_data': 'market_data_updates',
        'social_data': 'social_media_posts',
        'notifications': 'notification_alerts'
    }
    
    # Configuration APIs externes
    HELIUS_API_KEY = os.getenv('HELIUS_API_KEY', '')
    QUICKNODE_API_KEY = os.getenv('QUICKNODE_API_KEY', '')
    TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN', '')
    REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID', '')
    REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET', '')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    # Configuration des filtres par défaut
    DEFAULT_FILTER_CRITERIA = {
        'min_initial_market_cap_usd': 10000,      # 10k USD minimum
        'max_initial_market_cap_usd': 1000000,    # 1M USD maximum
        'min_liquidity_usd': 50000,               # 50k USD minimum
        'min_price_change_1h_percent': 5.0,       # +5% minimum sur 1h
        'min_volume_24h_usd': 10000,              # 10k USD minimum sur 24h
        'min_social_sentiment_score': 0.1,        # Sentiment légèrement positif
        'min_social_mentions_24h': 10,            # 10 mentions minimum
        'required_keywords': ['meme', 'coin', 'solana'],
        'excluded_keywords': ['scam', 'rug', 'fake']
    }
    
    # Configuration des notifications
    NOTIFICATION_CHANNELS = {
        'telegram_enabled': True,
        'email_enabled': False,
        'telegram_chat_id': os.getenv('TELEGRAM_CHAT_ID', ''),
        'email_address': os.getenv('EMAIL_ADDRESS', '')
    }
    
    # Configuration du logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'solana_meme_bot.log')
    
    # Configuration de performance
    MAX_CONCURRENT_REQUESTS = int(os.getenv('MAX_CONCURRENT_REQUESTS', 10))
    CACHE_TTL_SECONDS = int(os.getenv('CACHE_TTL_SECONDS', 300))  # 5 minutes
    WEBSOCKET_RECONNECT_DELAY = int(os.getenv('WEBSOCKET_RECONNECT_DELAY', 5))
    
    # Configuration des DEX supportés
    SUPPORTED_DEX = ['raydium', 'orca', 'jupiter']
    
    # Configuration des timeframes pour l'analyse
    PRICE_ANALYSIS_TIMEFRAMES = {
        '1h': 3600,    # 1 heure en secondes
        '24h': 86400,  # 24 heures en secondes
        '7d': 604800   # 7 jours en secondes
    }

