"""
Module de surveillance des réseaux sociaux
Intègre Twitter/X, Reddit et Telegram pour surveiller les mentions et l'engagement
"""
import asyncio
import aiohttp
import logging
import time
import re
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass
import json
from datetime import datetime, timedelta

from config import Config
from models import SocialMediaPost, EngagementMetrics
from sentiment_analyzer import SentimentAnalyzer

@dataclass
class SocialAlert:
    """Alerte basée sur l'activité sociale"""
    token_address: str
    platform: str
    alert_type: str  # 'mention_spike', 'sentiment_change', 'influencer_mention'
    description: str
    urgency: str  # 'low', 'medium', 'high'
    data: Dict[str, Any]
    timestamp: int

class TwitterMonitor:
    """Moniteur pour Twitter/X"""
    
    def __init__(self, config: Config, sentiment_analyzer: SentimentAnalyzer):
        self.config = config
        self.sentiment_analyzer = sentiment_analyzer
        self.logger = logging.getLogger(__name__)
        self.bearer_token = config.TWITTER_BEARER_TOKEN
        self.session = None
        
        # Mots-clés à surveiller
        self.crypto_keywords = [
            'solana', 'sol', 'meme coin', 'memecoin', 'defi', 'nft',
            'pump', 'moon', 'gem', 'altcoin', 'crypto', 'blockchain'
        ]
        
        # Comptes influents à surveiller
        self.influencer_accounts = [
            'elonmusk', 'VitalikButerin', 'cz_binance', 'SBF_FTX',
            'justinsuntron', 'aantonop', 'naval'
        ]
        
        # Cache des tweets récents pour éviter les doublons
        self.recent_tweets = set()
        self.last_cleanup = time.time()
    
    async def __aenter__(self):
        """Gestionnaire de contexte asynchrone - entrée"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Gestionnaire de contexte asynchrone - sortie"""
        if self.session:
            await self.session.close()
    
    async def start_monitoring(self, callback: Callable[[SocialMediaPost], None]):
        """Démarrer la surveillance Twitter"""
        if not self.bearer_token:
            self.logger.warning("Token Twitter manquant, surveillance désactivée")
            return
        
        self.logger.info("Démarrage de la surveillance Twitter...")
        
        while True:
            try:
                # Rechercher les tweets récents
                tweets = await self._search_recent_tweets()
                
                for tweet_data in tweets:
                    post = await self._process_tweet(tweet_data)
                    if post and post.post_id not in self.recent_tweets:
                        self.recent_tweets.add(post.post_id)
                        await callback(post)
                
                # Nettoyer le cache périodiquement
                await self._cleanup_cache()
                
                # Attendre avant la prochaine recherche
                await asyncio.sleep(30)  # Toutes les 30 secondes
                
            except Exception as e:
                self.logger.error(f"Erreur dans la surveillance Twitter: {e}")
                await asyncio.sleep(60)  # Attendre plus longtemps en cas d'erreur
    
    async def _search_recent_tweets(self) -> List[Dict]:
        """Rechercher les tweets récents"""
        try:
            # Construire la requête de recherche
            query = ' OR '.join(self.crypto_keywords)
            query += ' -is:retweet lang:en'  # Exclure les retweets, tweets en anglais seulement
            
            url = "https://api.twitter.com/2/tweets/search/recent"
            params = {
                'query': query,
                'max_results': 100,
                'tweet.fields': 'created_at,author_id,public_metrics,context_annotations',
                'user.fields': 'username,verified,public_metrics',
                'expansions': 'author_id'
            }
            
            headers = {
                'Authorization': f'Bearer {self.bearer_token}',
                'Content-Type': 'application/json'
            }
            
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('data', [])
                elif response.status == 429:
                    self.logger.warning("Limite de taux Twitter atteinte")
                    await asyncio.sleep(900)  # Attendre 15 minutes
                else:
                    self.logger.error(f"Erreur API Twitter: {response.status}")
                    
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche de tweets: {e}")
        
        return []
    
    async def _process_tweet(self, tweet_data: Dict) -> Optional[SocialMediaPost]:
        """Traiter un tweet et créer un objet SocialMediaPost"""
        try:
            tweet_id = tweet_data.get('id')
            text = tweet_data.get('text', '')
            created_at = tweet_data.get('created_at')
            author_id = tweet_data.get('author_id')
            
            # Métriques d'engagement
            metrics = tweet_data.get('public_metrics', {})
            engagement = EngagementMetrics(
                likes=metrics.get('like_count', 0),
                retweets=metrics.get('retweet_count', 0),
                comments=metrics.get('reply_count', 0),
                shares=metrics.get('quote_count', 0)
            )
            
            # Analyser le sentiment
            sentiment_result = await self.sentiment_analyzer.analyze_sentiment(text, 'crypto')
            
            # Extraire les mots-clés
            keywords = self._extract_keywords(text)
            
            # Détecter les mentions de tokens
            token_address = await self._detect_token_mentions(text)
            
            # Convertir la date
            timestamp = int(datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp())
            
            return SocialMediaPost(
                post_id=tweet_id,
                platform='Twitter',
                author=author_id,  # Dans une implémentation complète, résoudre le nom d'utilisateur
                timestamp=timestamp,
                content=text,
                keywords=keywords,
                sentiment_score=sentiment_result.score,
                engagement_metrics=engagement,
                related_token_mint_address=token_address
            )
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du tweet: {e}")
            return None
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extraire les mots-clés pertinents du texte"""
        keywords = []
        text_lower = text.lower()
        
        # Chercher les mots-clés crypto
        for keyword in self.crypto_keywords:
            if keyword in text_lower:
                keywords.append(keyword)
        
        # Extraire les hashtags
        hashtags = re.findall(r'#(\w+)', text)
        keywords.extend(hashtags)
        
        # Extraire les cashtags ($SYMBOL)
        cashtags = re.findall(r'\$([A-Z]{2,10})', text)
        keywords.extend(cashtags)
        
        return list(set(keywords))
    
    async def _detect_token_mentions(self, text: str) -> Optional[str]:
        """Détecter les mentions de tokens Solana dans le texte"""
        # Patterns pour les adresses Solana (base58, 32-44 caractères)
        solana_address_pattern = r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
        addresses = re.findall(solana_address_pattern, text)
        
        if addresses:
            # Retourner la première adresse trouvée
            # Dans une implémentation complète, valider que c'est bien une adresse de token
            return addresses[0]
        
        return None
    
    async def _cleanup_cache(self):
        """Nettoyer le cache des tweets récents"""
        current_time = time.time()
        if current_time - self.last_cleanup > 3600:  # Toutes les heures
            # Garder seulement les IDs des dernières 2 heures
            # Dans une implémentation complète, associer un timestamp à chaque ID
            if len(self.recent_tweets) > 1000:
                self.recent_tweets.clear()
            self.last_cleanup = current_time

class RedditMonitor:
    """Moniteur pour Reddit"""
    
    def __init__(self, config: Config, sentiment_analyzer: SentimentAnalyzer):
        self.config = config
        self.sentiment_analyzer = sentiment_analyzer
        self.logger = logging.getLogger(__name__)
        self.session = None
        
        # Subreddits à surveiller
        self.crypto_subreddits = [
            'CryptoCurrency', 'solana', 'SolanaNFTs', 'defi', 'altcoin',
            'CryptoMoonShots', 'SatoshiStreetBets', 'CryptoMarkets'
        ]
        
        # Cache des posts récents
        self.recent_posts = set()
    
    async def __aenter__(self):
        """Gestionnaire de contexte asynchrone - entrée"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Gestionnaire de contexte asynchrone - sortie"""
        if self.session:
            await self.session.close()
    
    async def start_monitoring(self, callback: Callable[[SocialMediaPost], None]):
        """Démarrer la surveillance Reddit"""
        self.logger.info("Démarrage de la surveillance Reddit...")
        
        while True:
            try:
                for subreddit in self.crypto_subreddits:
                    posts = await self._get_subreddit_posts(subreddit)
                    
                    for post_data in posts:
                        post = await self._process_reddit_post(post_data)
                        if post and post.post_id not in self.recent_posts:
                            self.recent_posts.add(post.post_id)
                            await callback(post)
                
                # Nettoyer le cache
                if len(self.recent_posts) > 2000:
                    self.recent_posts.clear()
                
                await asyncio.sleep(120)  # Toutes les 2 minutes
                
            except Exception as e:
                self.logger.error(f"Erreur dans la surveillance Reddit: {e}")
                await asyncio.sleep(300)  # Attendre 5 minutes en cas d'erreur
    
    async def _get_subreddit_posts(self, subreddit: str) -> List[Dict]:
        """Obtenir les posts récents d'un subreddit"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/new.json"
            params = {'limit': 25}
            
            headers = {
                'User-Agent': 'SolanaMemeBot/1.0 (by /u/your_username)'
            }
            
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('data', {}).get('children', [])
                else:
                    self.logger.warning(f"Erreur Reddit API pour r/{subreddit}: {response.status}")
                    
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des posts Reddit: {e}")
        
        return []
    
    async def _process_reddit_post(self, post_data: Dict) -> Optional[SocialMediaPost]:
        """Traiter un post Reddit"""
        try:
            post_info = post_data.get('data', {})
            
            post_id = post_info.get('id')
            title = post_info.get('title', '')
            selftext = post_info.get('selftext', '')
            author = post_info.get('author', '')
            created_utc = post_info.get('created_utc', 0)
            subreddit = post_info.get('subreddit', '')
            
            # Combiner titre et contenu
            full_text = f"{title} {selftext}".strip()
            
            # Métriques d'engagement
            engagement = EngagementMetrics(
                likes=post_info.get('ups', 0),
                comments=post_info.get('num_comments', 0),
                shares=0  # Reddit ne fournit pas cette métrique
            )
            
            # Analyser le sentiment
            sentiment_result = await self.sentiment_analyzer.analyze_sentiment(full_text, 'crypto')
            
            # Extraire les mots-clés
            keywords = self._extract_reddit_keywords(full_text, subreddit)
            
            # Détecter les mentions de tokens
            token_address = await self._detect_token_mentions(full_text)
            
            return SocialMediaPost(
                post_id=post_id,
                platform='Reddit',
                author=author,
                timestamp=int(created_utc),
                content=full_text,
                keywords=keywords,
                sentiment_score=sentiment_result.score,
                engagement_metrics=engagement,
                related_token_mint_address=token_address
            )
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du post Reddit: {e}")
            return None
    
    def _extract_reddit_keywords(self, text: str, subreddit: str) -> List[str]:
        """Extraire les mots-clés d'un post Reddit"""
        keywords = [subreddit.lower()]
        text_lower = text.lower()
        
        # Mots-clés crypto communs
        crypto_terms = [
            'solana', 'sol', 'meme', 'coin', 'token', 'defi', 'nft',
            'pump', 'dump', 'moon', 'hodl', 'diamond', 'hands'
        ]
        
        for term in crypto_terms:
            if term in text_lower:
                keywords.append(term)
        
        return list(set(keywords))
    
    async def _detect_token_mentions(self, text: str) -> Optional[str]:
        """Détecter les mentions de tokens dans le texte Reddit"""
        # Même logique que Twitter
        solana_address_pattern = r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
        addresses = re.findall(solana_address_pattern, text)
        
        if addresses:
            return addresses[0]
        
        return None

class TelegramMonitor:
    """Moniteur pour Telegram"""
    
    def __init__(self, config: Config, sentiment_analyzer: SentimentAnalyzer):
        self.config = config
        self.sentiment_analyzer = sentiment_analyzer
        self.logger = logging.getLogger(__name__)
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.session = None
        
        # Canaux publics à surveiller
        self.crypto_channels = [
            '@solana_community',
            '@defi_news',
            '@crypto_signals',
            '@meme_coins'
        ]
        
        # Cache des messages récents
        self.recent_messages = set()
    
    async def __aenter__(self):
        """Gestionnaire de contexte asynchrone - entrée"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Gestionnaire de contexte asynchrone - sortie"""
        if self.session:
            await self.session.close()
    
    async def start_monitoring(self, callback: Callable[[SocialMediaPost], None]):
        """Démarrer la surveillance Telegram"""
        if not self.bot_token:
            self.logger.warning("Token Telegram manquant, surveillance désactivée")
            return
        
        self.logger.info("Démarrage de la surveillance Telegram...")
        
        # Note: La surveillance des canaux Telegram publics nécessite des permissions spéciales
        # Cette implémentation est simplifiée pour la démonstration
        
        while True:
            try:
                # Dans une implémentation réelle, utiliser l'API MTProto ou des webhooks
                await self._simulate_telegram_monitoring(callback)
                await asyncio.sleep(60)  # Toutes les minutes
                
            except Exception as e:
                self.logger.error(f"Erreur dans la surveillance Telegram: {e}")
                await asyncio.sleep(300)
    
    async def _simulate_telegram_monitoring(self, callback: Callable[[SocialMediaPost], None]):
        """Simuler la surveillance Telegram (pour démonstration)"""
        # Dans une implémentation réelle, ceci serait remplacé par de vrais appels API
        self.logger.debug("Simulation de la surveillance Telegram...")
        
        # Exemple de message simulé
        if time.time() % 300 < 1:  # Toutes les 5 minutes environ
            simulated_post = SocialMediaPost(
                post_id=f"tg_{int(time.time())}",
                platform='Telegram',
                author='crypto_trader_123',
                timestamp=int(time.time()),
                content="New Solana meme coin just launched! 🚀 Looking bullish!",
                keywords=['solana', 'meme', 'coin', 'bullish'],
                sentiment_score=0.7,
                engagement_metrics=EngagementMetrics(likes=15, comments=3),
                related_token_mint_address=None
            )
            
            await callback(simulated_post)

class SocialMonitor:
    """Moniteur principal des réseaux sociaux"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.sentiment_analyzer = SentimentAnalyzer(config)
        
        # Moniteurs spécialisés
        self.twitter_monitor = TwitterMonitor(config, self.sentiment_analyzer)
        self.reddit_monitor = RedditMonitor(config, self.sentiment_analyzer)
        self.telegram_monitor = TelegramMonitor(config, self.sentiment_analyzer)
        
        # Callbacks pour les événements
        self.callbacks = {
            'social_post': [],
            'social_alert': []
        }
        
        # Statistiques
        self.stats = {
            'posts_processed': 0,
            'alerts_generated': 0,
            'sentiment_analyses': 0
        }
        
        # Détection d'alertes
        self.mention_counts = {}
        self.sentiment_history = {}
        
    def add_callback(self, event_type: str, callback: Callable):
        """Ajouter un callback pour un type d'événement"""
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)
    
    async def start_monitoring(self):
        """Démarrer la surveillance de tous les réseaux sociaux"""
        self.logger.info("Démarrage de la surveillance des réseaux sociaux...")
        
        async with self.sentiment_analyzer:
            # Démarrer tous les moniteurs en parallèle
            tasks = [
                asyncio.create_task(self.twitter_monitor.start_monitoring(self._handle_social_post)),
                asyncio.create_task(self.reddit_monitor.start_monitoring(self._handle_social_post)),
                asyncio.create_task(self.telegram_monitor.start_monitoring(self._handle_social_post)),
                asyncio.create_task(self._alert_detector())
            ]
            
            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                self.logger.error(f"Erreur dans la surveillance sociale: {e}")
    
    async def _handle_social_post(self, post: SocialMediaPost):
        """Gérer un nouveau post de réseau social"""
        try:
            self.stats['posts_processed'] += 1
            
            # Mettre à jour les statistiques de mentions
            if post.related_token_mint_address:
                self._update_mention_stats(post.related_token_mint_address, post.platform)
            
            # Mettre à jour l'historique de sentiment
            self._update_sentiment_history(post)
            
            # Détecter les alertes
            alerts = await self._detect_alerts(post)
            for alert in alerts:
                await self._handle_social_alert(alert)
            
            # Notifier les callbacks
            for callback in self.callbacks['social_post']:
                try:
                    await callback(post)
                except Exception as e:
                    self.logger.error(f"Erreur dans le callback social_post: {e}")
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du post social: {e}")
    
    def _update_mention_stats(self, token_address: str, platform: str):
        """Mettre à jour les statistiques de mentions"""
        current_hour = int(time.time() // 3600)
        
        if token_address not in self.mention_counts:
            self.mention_counts[token_address] = {}
        
        if current_hour not in self.mention_counts[token_address]:
            self.mention_counts[token_address][current_hour] = {}
        
        if platform not in self.mention_counts[token_address][current_hour]:
            self.mention_counts[token_address][current_hour][platform] = 0
        
        self.mention_counts[token_address][current_hour][platform] += 1
    
    def _update_sentiment_history(self, post: SocialMediaPost):
        """Mettre à jour l'historique de sentiment"""
        if post.related_token_mint_address:
            token_address = post.related_token_mint_address
            
            if token_address not in self.sentiment_history:
                self.sentiment_history[token_address] = []
            
            self.sentiment_history[token_address].append({
                'timestamp': post.timestamp,
                'sentiment': post.sentiment_score,
                'platform': post.platform
            })
            
            # Garder seulement les 100 derniers points
            if len(self.sentiment_history[token_address]) > 100:
                self.sentiment_history[token_address] = self.sentiment_history[token_address][-100:]
    
    async def _detect_alerts(self, post: SocialMediaPost) -> List[SocialAlert]:
        """Détecter les alertes basées sur le post"""
        alerts = []
        
        try:
            # Alerte pour sentiment très positif ou négatif
            if abs(post.sentiment_score) > 0.8:
                alerts.append(SocialAlert(
                    token_address=post.related_token_mint_address or 'unknown',
                    platform=post.platform,
                    alert_type='extreme_sentiment',
                    description=f"Sentiment extrême détecté: {post.sentiment_score:.2f}",
                    urgency='medium' if abs(post.sentiment_score) > 0.9 else 'low',
                    data={'post_id': post.post_id, 'sentiment': post.sentiment_score},
                    timestamp=post.timestamp
                ))
            
            # Alerte pour engagement élevé
            total_engagement = (post.engagement_metrics.likes + 
                              post.engagement_metrics.retweets + 
                              post.engagement_metrics.comments)
            
            if total_engagement > 1000:  # Seuil configurable
                alerts.append(SocialAlert(
                    token_address=post.related_token_mint_address or 'unknown',
                    platform=post.platform,
                    alert_type='high_engagement',
                    description=f"Engagement élevé: {total_engagement} interactions",
                    urgency='medium',
                    data={'post_id': post.post_id, 'engagement': total_engagement},
                    timestamp=post.timestamp
                ))
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la détection d'alertes: {e}")
        
        return alerts
    
    async def _handle_social_alert(self, alert: SocialAlert):
        """Gérer une alerte sociale"""
        self.stats['alerts_generated'] += 1
        self.logger.info(f"Alerte sociale: {alert.description}")
        
        # Notifier les callbacks
        for callback in self.callbacks['social_alert']:
            try:
                await callback(alert)
            except Exception as e:
                self.logger.error(f"Erreur dans le callback social_alert: {e}")
    
    async def _alert_detector(self):
        """Détecteur d'alertes périodique"""
        while True:
            try:
                await asyncio.sleep(300)  # Toutes les 5 minutes
                
                # Détecter les pics de mentions
                await self._detect_mention_spikes()
                
                # Détecter les changements de sentiment
                await self._detect_sentiment_changes()
                
            except Exception as e:
                self.logger.error(f"Erreur dans le détecteur d'alertes: {e}")
    
    async def _detect_mention_spikes(self):
        """Détecter les pics de mentions"""
        current_hour = int(time.time() // 3600)
        
        for token_address, hourly_data in self.mention_counts.items():
            if current_hour in hourly_data:
                current_mentions = sum(hourly_data[current_hour].values())
                
                # Comparer avec l'heure précédente
                prev_hour = current_hour - 1
                prev_mentions = sum(hourly_data.get(prev_hour, {}).values())
                
                if prev_mentions > 0 and current_mentions > prev_mentions * 3:  # 3x augmentation
                    alert = SocialAlert(
                        token_address=token_address,
                        platform='multiple',
                        alert_type='mention_spike',
                        description=f"Pic de mentions: {current_mentions} vs {prev_mentions}",
                        urgency='high',
                        data={'current': current_mentions, 'previous': prev_mentions},
                        timestamp=int(time.time())
                    )
                    
                    await self._handle_social_alert(alert)
    
    async def _detect_sentiment_changes(self):
        """Détecter les changements significatifs de sentiment"""
        for token_address, history in self.sentiment_history.items():
            if len(history) >= 10:  # Minimum 10 points de données
                recent_sentiments = [h['sentiment'] for h in history[-10:]]
                older_sentiments = [h['sentiment'] for h in history[-20:-10]] if len(history) >= 20 else []
                
                if older_sentiments:
                    recent_avg = sum(recent_sentiments) / len(recent_sentiments)
                    older_avg = sum(older_sentiments) / len(older_sentiments)
                    
                    change = recent_avg - older_avg
                    
                    if abs(change) > 0.5:  # Changement significatif
                        alert = SocialAlert(
                            token_address=token_address,
                            platform='multiple',
                            alert_type='sentiment_change',
                            description=f"Changement de sentiment: {change:+.2f}",
                            urgency='medium',
                            data={'change': change, 'recent_avg': recent_avg, 'older_avg': older_avg},
                            timestamp=int(time.time())
                        )
                        
                        await self._handle_social_alert(alert)
    
    def get_token_social_metrics(self, token_address: str) -> Dict[str, Any]:
        """Obtenir les métriques sociales d'un token"""
        current_hour = int(time.time() // 3600)
        
        # Mentions récentes
        recent_mentions = 0
        if token_address in self.mention_counts:
            for hour in range(current_hour - 23, current_hour + 1):  # Dernières 24h
                if hour in self.mention_counts[token_address]:
                    recent_mentions += sum(self.mention_counts[token_address][hour].values())
        
        # Sentiment moyen récent
        recent_sentiment = 0.0
        if token_address in self.sentiment_history:
            recent_history = [h for h in self.sentiment_history[token_address] 
                            if h['timestamp'] > time.time() - 86400]  # Dernières 24h
            if recent_history:
                recent_sentiment = sum(h['sentiment'] for h in recent_history) / len(recent_history)
        
        return {
            'mentions_24h': recent_mentions,
            'average_sentiment_24h': recent_sentiment,
            'sentiment_data_points': len(self.sentiment_history.get(token_address, [])),
            'platforms_active': list(set(h['platform'] for h in self.sentiment_history.get(token_address, [])))
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques du moniteur social"""
        return {
            **self.stats,
            'tracked_tokens': len(self.mention_counts),
            'sentiment_analyzer_stats': self.sentiment_analyzer.get_stats()
        }

