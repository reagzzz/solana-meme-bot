"""
Module de filtrage en flux (Stream Filtering)
Implémente les algorithmes sophistiqués pour le traitement en temps réel
"""
import asyncio
import hashlib
import time
import logging
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict, deque
from dataclasses import dataclass
import json
import redis
from kafka import KafkaProducer, KafkaConsumer
import threading

from config import Config
from models import TokenData, FilterCriteria, NotificationMessage

@dataclass
class StreamEvent:
    """Événement dans le flux de données"""
    event_type: str  # 'new_token', 'price_update', 'social_mention'
    timestamp: int
    data: Dict[str, Any]
    source: str

class HashingManager:
    """Gestionnaire des algorithmes de hachage pour l'optimisation"""
    
    def __init__(self):
        self.token_hashes = {}
        self.content_hashes = set()
    
    def hash_token_address(self, mint_address: str) -> str:
        """Hacher une adresse de token pour l'indexation rapide"""
        return hashlib.sha256(mint_address.encode()).hexdigest()[:16]
    
    def hash_content(self, content: str) -> str:
        """Hacher du contenu pour la déduplication"""
        return hashlib.md5(content.encode()).hexdigest()
    
    def is_duplicate_content(self, content: str) -> bool:
        """Vérifier si le contenu est un doublon"""
        content_hash = self.hash_content(content)
        if content_hash in self.content_hashes:
            return True
        self.content_hashes.add(content_hash)
        return False
    
    def cleanup_old_hashes(self, max_age_seconds: int = 3600):
        """Nettoyer les anciens hashes pour éviter la surcharge mémoire"""
        # Dans une implémentation complète, on garderait un timestamp pour chaque hash
        if len(self.content_hashes) > 10000:
            self.content_hashes.clear()

class CacheManager:
    """Gestionnaire de cache pour l'optimisation des performances"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.local_cache = {}
        self.cache_stats = {'hits': 0, 'misses': 0}
    
    async def get(self, key: str) -> Optional[Any]:
        """Récupérer une valeur du cache (local puis Redis)"""
        # Vérifier le cache local d'abord
        if key in self.local_cache:
            entry = self.local_cache[key]
            if time.time() - entry['timestamp'] < 60:  # Cache local valide 1 minute
                self.cache_stats['hits'] += 1
                return entry['value']
            else:
                del self.local_cache[key]
        
        # Vérifier Redis
        try:
            value = self.redis.get(key)
            if value:
                decoded_value = json.loads(value.decode('utf-8'))
                # Mettre en cache localement
                self.local_cache[key] = {
                    'value': decoded_value,
                    'timestamp': time.time()
                }
                self.cache_stats['hits'] += 1
                return decoded_value
        except Exception as e:
            logging.error(f"Erreur cache Redis: {e}")
        
        self.cache_stats['misses'] += 1
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 300):
        """Stocker une valeur dans le cache"""
        try:
            # Stocker dans Redis
            json_value = json.dumps(value)
            self.redis.setex(key, ttl, json_value)
            
            # Stocker localement
            self.local_cache[key] = {
                'value': value,
                'timestamp': time.time()
            }
        except Exception as e:
            logging.error(f"Erreur lors de la mise en cache: {e}")
    
    def get_stats(self) -> Dict[str, int]:
        """Obtenir les statistiques du cache"""
        total = self.cache_stats['hits'] + self.cache_stats['misses']
        hit_rate = (self.cache_stats['hits'] / total * 100) if total > 0 else 0
        return {
            **self.cache_stats,
            'hit_rate_percent': round(hit_rate, 2)
        }

class CollaborativeFilter:
    """Algorithme de filtrage collaboratif pour les recommandations"""
    
    def __init__(self):
        self.user_preferences = defaultdict(dict)
        self.token_similarities = {}
        self.user_similarities = {}
    
    def add_user_interaction(self, user_id: str, token_address: str, interaction_type: str, score: float):
        """Ajouter une interaction utilisateur"""
        if token_address not in self.user_preferences[user_id]:
            self.user_preferences[user_id][token_address] = []
        
        self.user_preferences[user_id][token_address].append({
            'type': interaction_type,
            'score': score,
            'timestamp': time.time()
        })
    
    def calculate_token_similarity(self, token1: str, token2: str) -> float:
        """Calculer la similarité entre deux tokens basée sur les interactions utilisateurs"""
        users_token1 = set()
        users_token2 = set()
        
        for user_id, tokens in self.user_preferences.items():
            if token1 in tokens:
                users_token1.add(user_id)
            if token2 in tokens:
                users_token2.add(user_id)
        
        # Similarité de Jaccard
        intersection = len(users_token1.intersection(users_token2))
        union = len(users_token1.union(users_token2))
        
        return intersection / union if union > 0 else 0.0
    
    def recommend_similar_tokens(self, token_address: str, limit: int = 5) -> List[Tuple[str, float]]:
        """Recommander des tokens similaires"""
        similarities = []
        
        for other_token in self.get_all_tokens():
            if other_token != token_address:
                similarity = self.calculate_token_similarity(token_address, other_token)
                if similarity > 0:
                    similarities.append((other_token, similarity))
        
        return sorted(similarities, key=lambda x: x[1], reverse=True)[:limit]
    
    def get_all_tokens(self) -> Set[str]:
        """Obtenir tous les tokens connus"""
        tokens = set()
        for user_tokens in self.user_preferences.values():
            tokens.update(user_tokens.keys())
        return tokens

class GraphAnalyzer:
    """Analyseur de graphe pour les connexions de communauté"""
    
    def __init__(self):
        self.social_graph = defaultdict(set)
        self.token_communities = defaultdict(set)
        self.influence_scores = {}
    
    def add_social_connection(self, user1: str, user2: str, connection_type: str = 'mention'):
        """Ajouter une connexion sociale"""
        self.social_graph[user1].add(user2)
        if connection_type == 'bidirectional':
            self.social_graph[user2].add(user1)
    
    def add_token_mention(self, user: str, token_address: str):
        """Ajouter une mention de token par un utilisateur"""
        self.token_communities[token_address].add(user)
    
    def calculate_influence_score(self, user: str) -> float:
        """Calculer le score d'influence d'un utilisateur"""
        if user in self.influence_scores:
            return self.influence_scores[user]
        
        # Score basé sur le nombre de connexions (degré du nœud)
        connections = len(self.social_graph[user])
        
        # Score basé sur l'influence des connexions (PageRank simplifié)
        influence_from_connections = 0.0
        for connected_user in self.social_graph[user]:
            # Récursion limitée pour éviter les cycles infinis
            if connected_user != user:
                influence_from_connections += len(self.social_graph[connected_user]) * 0.1
        
        total_score = connections + influence_from_connections
        self.influence_scores[user] = total_score
        return total_score
    
    def get_community_strength(self, token_address: str) -> float:
        """Calculer la force de la communauté autour d'un token"""
        community = self.token_communities[token_address]
        if not community:
            return 0.0
        
        # Calculer la force basée sur la taille et l'influence
        total_influence = sum(self.calculate_influence_score(user) for user in community)
        community_size = len(community)
        
        # Score normalisé
        strength = (total_influence / community_size) if community_size > 0 else 0.0
        return min(strength / 100, 1.0)  # Normaliser entre 0 et 1
    
    def detect_trending_tokens(self, time_window: int = 3600) -> List[Tuple[str, float]]:
        """Détecter les tokens tendance basés sur l'activité communautaire"""
        current_time = time.time()
        token_scores = []
        
        for token_address, community in self.token_communities.items():
            strength = self.get_community_strength(token_address)
            size = len(community)
            
            # Score combiné: force de la communauté + taille
            combined_score = strength * 0.7 + (size / 100) * 0.3
            token_scores.append((token_address, combined_score))
        
        return sorted(token_scores, key=lambda x: x[1], reverse=True)

class StreamFilter:
    """Filtre principal pour le traitement en flux"""
    
    def __init__(self, config: Config, redis_client):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Composants d'analyse
        self.hashing_manager = HashingManager()
        self.cache_manager = CacheManager(redis_client)
        self.collaborative_filter = CollaborativeFilter()
        self.graph_analyzer = GraphAnalyzer()
        
        # Configuration Kafka
        self.producer = KafkaProducer(
            bootstrap_servers=[config.KAFKA_BOOTSTRAP_SERVERS],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        # Files d'événements
        self.event_queue = asyncio.Queue(maxsize=1000)
        self.processing_stats = {
            'events_processed': 0,
            'tokens_filtered': 0,
            'notifications_sent': 0
        }
        
        # Critères de filtrage
        self.filter_criteria = FilterCriteria.from_dict(config.DEFAULT_FILTER_CRITERIA)
        
        # État du système
        self.running = False
        self.batch_buffer = deque(maxlen=100)
        self.last_batch_process = time.time()
    
    async def start_filtering(self):
        """Démarrer le système de filtrage"""
        self.running = True
        self.logger.info("Démarrage du système de filtrage en flux...")
        
        # Démarrer les tâches de traitement
        tasks = [
            asyncio.create_task(self._stream_processor()),
            asyncio.create_task(self._batch_processor()),
            asyncio.create_task(self._stats_reporter())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            self.logger.error(f"Erreur dans le système de filtrage: {e}")
        finally:
            self.producer.close()
    
    async def stop_filtering(self):
        """Arrêter le système de filtrage"""
        self.running = False
        self.logger.info("Arrêt du système de filtrage...")
    
    async def add_event(self, event: StreamEvent):
        """Ajouter un événement au flux de traitement"""
        try:
            await self.event_queue.put(event)
        except asyncio.QueueFull:
            self.logger.warning("File d'événements pleine, événement ignoré")
    
    async def _stream_processor(self):
        """Processeur principal du flux d'événements"""
        self.logger.info("Processeur de flux démarré")
        
        while self.running:
            try:
                # Traitement avec timeout pour éviter le blocage
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                await self._process_stream_event(event)
                self.processing_stats['events_processed'] += 1
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Erreur lors du traitement d'événement: {e}")
    
    async def _process_stream_event(self, event: StreamEvent):
        """Traiter un événement individuel du flux"""
        try:
            if event.event_type == 'new_token':
                await self._process_new_token_event(event)
            elif event.event_type == 'price_update':
                await self._process_price_update_event(event)
            elif event.event_type == 'social_mention':
                await self._process_social_mention_event(event)
            
            # Ajouter à la file de traitement par lot pour analyse approfondie
            self.batch_buffer.append(event)
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement de l'événement {event.event_type}: {e}")
    
    async def _process_new_token_event(self, event: StreamEvent):
        """Traiter un événement de nouveau token"""
        token_data = TokenData.from_dict(event.data)
        
        # Vérification de déduplication avec hachage
        token_hash = self.hashing_manager.hash_token_address(token_data.mint_address)
        cache_key = f"processed_token:{token_hash}"
        
        if await self.cache_manager.get(cache_key):
            self.logger.debug(f"Token déjà traité: {token_data.symbol}")
            return
        
        # Appliquer les filtres en temps réel
        matches, reasons = self.filter_criteria.matches_token(token_data)
        
        if matches:
            self.logger.info(f"Token {token_data.symbol} correspond aux critères!")
            
            # Enrichir avec l'analyse collaborative et de graphe
            await self._enrich_token_analysis(token_data)
            
            # Créer et envoyer la notification
            notification = NotificationMessage(
                token_data=token_data,
                reasons=reasons,
                timestamp=int(time.time()),
                channels=['telegram', 'email']
            )
            
            await self._send_notification(notification)
            self.processing_stats['notifications_sent'] += 1
        
        # Marquer comme traité
        await self.cache_manager.set(cache_key, True, ttl=3600)
        self.processing_stats['tokens_filtered'] += 1
    
    async def _process_price_update_event(self, event: StreamEvent):
        """Traiter un événement de mise à jour de prix"""
        mint_address = event.data.get('mint_address')
        new_price = event.data.get('price')
        
        if not mint_address or not new_price:
            return
        
        # Mettre à jour le cache des prix
        cache_key = f"price:{mint_address}"
        await self.cache_manager.set(cache_key, {
            'price': new_price,
            'timestamp': event.timestamp
        })
        
        # Vérifier si cela déclenche une alerte de prix
        await self._check_price_alerts(mint_address, new_price)
    
    async def _process_social_mention_event(self, event: StreamEvent):
        """Traiter un événement de mention sociale"""
        user = event.data.get('user')
        token_address = event.data.get('token_address')
        content = event.data.get('content', '')
        
        if not user or not token_address:
            return
        
        # Vérifier la déduplication du contenu
        if self.hashing_manager.is_duplicate_content(content):
            return
        
        # Ajouter au graphe social
        self.graph_analyzer.add_token_mention(user, token_address)
        
        # Ajouter à l'analyse collaborative
        sentiment_score = event.data.get('sentiment_score', 0.0)
        self.collaborative_filter.add_user_interaction(
            user, token_address, 'mention', sentiment_score
        )
    
    async def _enrich_token_analysis(self, token_data: TokenData):
        """Enrichir l'analyse d'un token avec les algorithmes avancés"""
        try:
            # Analyse de la communauté via graphe
            community_strength = self.graph_analyzer.get_community_strength(token_data.mint_address)
            token_data.community_engagement_score = community_strength
            
            # Recommandations collaboratives
            similar_tokens = self.collaborative_filter.recommend_similar_tokens(
                token_data.mint_address, limit=3
            )
            
            # Enrichir les métadonnées (pour logging/debug)
            enrichment_data = {
                'community_strength': community_strength,
                'similar_tokens': similar_tokens,
                'analysis_timestamp': time.time()
            }
            
            self.logger.info(f"Token {token_data.symbol} enrichi: {enrichment_data}")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'enrichissement du token {token_data.mint_address}: {e}")
    
    async def _send_notification(self, notification: NotificationMessage):
        """Envoyer une notification via Kafka"""
        try:
            notification_data = notification.to_dict()
            
            self.producer.send(
                self.config.KAFKA_TOPICS['notifications'],
                value=notification_data
            )
            
            self.logger.info(f"Notification envoyée pour {notification.token_data.symbol}")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi de notification: {e}")
    
    async def _check_price_alerts(self, mint_address: str, new_price: float):
        """Vérifier les alertes de prix"""
        try:
            # Récupérer le prix précédent
            cache_key = f"prev_price:{mint_address}"
            prev_data = await self.cache_manager.get(cache_key)
            
            if prev_data:
                prev_price = prev_data.get('price', 0)
                if prev_price > 0:
                    price_change = ((new_price - prev_price) / prev_price) * 100
                    
                    # Alerte pour changements significatifs (>10%)
                    if abs(price_change) > 10:
                        alert_data = {
                            'type': 'price_alert',
                            'mint_address': mint_address,
                            'price_change_percent': price_change,
                            'old_price': prev_price,
                            'new_price': new_price,
                            'timestamp': time.time()
                        }
                        
                        self.producer.send(
                            self.config.KAFKA_TOPICS['notifications'],
                            value=alert_data
                        )
            
            # Sauvegarder le prix actuel
            await self.cache_manager.set(cache_key, {'price': new_price})
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des alertes de prix: {e}")
    
    async def _batch_processor(self):
        """Processeur par lot pour les analyses approfondies"""
        self.logger.info("Processeur par lot démarré")
        
        while self.running:
            try:
                current_time = time.time()
                
                # Traiter par lot toutes les 30 secondes
                if current_time - self.last_batch_process > 30:
                    await self._process_batch()
                    self.last_batch_process = current_time
                
                await asyncio.sleep(5)
                
            except Exception as e:
                self.logger.error(f"Erreur dans le processeur par lot: {e}")
    
    async def _process_batch(self):
        """Traiter un lot d'événements pour analyse approfondie"""
        if not self.batch_buffer:
            return
        
        self.logger.info(f"Traitement par lot de {len(self.batch_buffer)} événements")
        
        try:
            # Analyser les tendances
            trending_tokens = self.graph_analyzer.detect_trending_tokens()
            
            if trending_tokens:
                self.logger.info(f"Tokens tendance détectés: {trending_tokens[:5]}")
            
            # Nettoyer les anciens hashes
            self.hashing_manager.cleanup_old_hashes()
            
            # Vider le buffer
            self.batch_buffer.clear()
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement par lot: {e}")
    
    async def _stats_reporter(self):
        """Reporter les statistiques périodiquement"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Toutes les minutes
                
                cache_stats = self.cache_manager.get_stats()
                
                stats = {
                    **self.processing_stats,
                    **cache_stats,
                    'queue_size': self.event_queue.qsize(),
                    'batch_buffer_size': len(self.batch_buffer),
                    'known_tokens': len(self.collaborative_filter.get_all_tokens())
                }
                
                self.logger.info(f"Statistiques du système: {stats}")
                
            except Exception as e:
                self.logger.error(f"Erreur lors du rapport de statistiques: {e}")
    
    def update_filter_criteria(self, new_criteria: FilterCriteria):
        """Mettre à jour les critères de filtrage"""
        self.filter_criteria = new_criteria
        self.logger.info("Critères de filtrage mis à jour")
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques complètes du système"""
        return {
            'processing_stats': self.processing_stats,
            'cache_stats': self.cache_manager.get_stats(),
            'queue_size': self.event_queue.qsize(),
            'batch_buffer_size': len(self.batch_buffer),
            'collaborative_filter_tokens': len(self.collaborative_filter.get_all_tokens()),
            'social_graph_users': len(self.graph_analyzer.social_graph),
            'running': self.running
        }

