"""
Modèles de données pour le Bot de Trading Meme Coins Solana
"""
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime
import json

@dataclass
class TokenData:
    """Structure de données pour un token Solana"""
    mint_address: str
    symbol: str
    name: str
    creation_timestamp: int
    supply: int
    decimals: int
    current_price_usd: float
    market_cap_usd: float
    liquidity_usd: float
    volume_24h_usd: float
    price_change_1h_percent: float
    price_change_24h_percent: float
    social_sentiment_score: float
    social_mentions_24h: int
    community_engagement_score: float
    last_updated_timestamp: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir en dictionnaire pour stockage/transmission"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TokenData':
        """Créer une instance à partir d'un dictionnaire"""
        return cls(**data)
    
    def to_json(self) -> str:
        """Convertir en JSON"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> 'TokenData':
        """Créer une instance à partir d'un JSON"""
        return cls.from_dict(json.loads(json_str))

@dataclass
class TransactionEvent:
    """Structure de données pour un événement de transaction"""
    transaction_id: str
    block_number: int
    timestamp: int
    mint_address: str
    sender_address: str
    receiver_address: str
    amount: float
    transaction_type: str  # 'swap', 'transfer', 'mint', etc.
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TransactionEvent':
        return cls(**data)

@dataclass
class EngagementMetrics:
    """Métriques d'engagement pour les réseaux sociaux"""
    likes: int = 0
    retweets: int = 0
    comments: int = 0
    shares: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class SocialMediaPost:
    """Structure de données pour un post de réseau social"""
    post_id: str
    platform: str  # 'Twitter', 'Reddit', 'Telegram'
    author: str
    timestamp: int
    content: str
    keywords: List[str]
    sentiment_score: float  # -1.0 à 1.0
    engagement_metrics: EngagementMetrics
    related_token_mint_address: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['engagement_metrics'] = self.engagement_metrics.to_dict()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SocialMediaPost':
        engagement_data = data.pop('engagement_metrics', {})
        engagement = EngagementMetrics(**engagement_data)
        return cls(engagement_metrics=engagement, **data)

@dataclass
class FilterCriteria:
    """Critères de filtrage configurables"""
    min_initial_market_cap_usd: float
    max_initial_market_cap_usd: float
    min_liquidity_usd: float
    min_price_change_1h_percent: float
    min_volume_24h_usd: float
    min_social_sentiment_score: float
    min_social_mentions_24h: int
    required_keywords: List[str]
    excluded_keywords: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FilterCriteria':
        return cls(**data)
    
    def matches_token(self, token: TokenData) -> tuple[bool, List[str]]:
        """
        Vérifie si un token correspond aux critères de filtrage
        Retourne (match, raisons) où raisons est la liste des critères remplis
        """
        reasons = []
        
        # Vérifier la capitalisation boursière
        if (self.min_initial_market_cap_usd <= token.market_cap_usd <= 
            self.max_initial_market_cap_usd):
            reasons.append(f"Capitalisation boursière: ${token.market_cap_usd:,.0f}")
        else:
            return False, []
        
        # Vérifier la liquidité
        if token.liquidity_usd >= self.min_liquidity_usd:
            reasons.append(f"Liquidité: ${token.liquidity_usd:,.0f}")
        else:
            return False, []
        
        # Vérifier la hausse de prix
        if token.price_change_1h_percent >= self.min_price_change_1h_percent:
            reasons.append(f"Hausse 1h: +{token.price_change_1h_percent:.1f}%")
        else:
            return False, []
        
        # Vérifier le volume
        if token.volume_24h_usd >= self.min_volume_24h_usd:
            reasons.append(f"Volume 24h: ${token.volume_24h_usd:,.0f}")
        else:
            return False, []
        
        # Vérifier le sentiment social
        if token.social_sentiment_score >= self.min_social_sentiment_score:
            reasons.append(f"Sentiment: {token.social_sentiment_score:.2f}")
        else:
            return False, []
        
        # Vérifier les mentions sociales
        if token.social_mentions_24h >= self.min_social_mentions_24h:
            reasons.append(f"Mentions 24h: {token.social_mentions_24h}")
        else:
            return False, []
        
        return True, reasons

@dataclass
class NotificationMessage:
    """Structure pour les messages de notification"""
    token_data: TokenData
    reasons: List[str]
    timestamp: int
    channels: List[str]  # ['telegram', 'email']
    
    def format_message(self) -> str:
        """Formater le message pour l'envoi"""
        message = f"🚨 Nouveau Meme Coin Détecté sur Solana! 🚨\n\n"
        message += f"Nom: {self.token_data.name}\n"
        message += f"Symbole: {self.token_data.symbol}\n"
        message += f"Adresse: {self.token_data.mint_address}\n\n"
        message += "Raisons de sélection:\n"
        for reason in self.reasons:
            message += f"- {reason}\n"
        message += f"\nPrix actuel: ${self.token_data.current_price_usd:.6f}\n"
        message += f"Consulter: https://birdeye.so/token/{self.token_data.mint_address}"
        return message
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'token_data': self.token_data.to_dict(),
            'reasons': self.reasons,
            'timestamp': self.timestamp,
            'channels': self.channels
        }

class TokenCache:
    """Classe utilitaire pour la gestion du cache des tokens"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.ttl = 300  # 5 minutes par défaut
    
    def get_token(self, mint_address: str) -> Optional[TokenData]:
        """Récupérer un token du cache"""
        try:
            data = self.redis.get(f"token:{mint_address}")
            if data:
                return TokenData.from_json(data.decode('utf-8'))
        except Exception as e:
            print(f"Erreur lors de la récupération du cache: {e}")
        return None
    
    def set_token(self, token: TokenData, ttl: Optional[int] = None) -> bool:
        """Stocker un token dans le cache"""
        try:
            key = f"token:{token.mint_address}"
            value = token.to_json()
            return self.redis.setex(key, ttl or self.ttl, value)
        except Exception as e:
            print(f"Erreur lors de la mise en cache: {e}")
            return False
    
    def delete_token(self, mint_address: str) -> bool:
        """Supprimer un token du cache"""
        try:
            return bool(self.redis.delete(f"token:{mint_address}"))
        except Exception as e:
            print(f"Erreur lors de la suppression du cache: {e}")
            return False

