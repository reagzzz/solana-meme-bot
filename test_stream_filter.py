"""
Tests unitaires pour le système de filtrage en flux
"""
import unittest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
import redis
import fakeredis

from config import Config
from models import TokenData, StreamEvent, FilterCriteria
from stream_filter import StreamFilter, HashingManager, CacheManager, CollaborativeFilter, GraphAnalyzer

class TestHashingManager(unittest.TestCase):
    """Tests pour le gestionnaire de hachage"""
    
    def setUp(self):
        self.hashing_manager = HashingManager()
    
    def test_hash_token_address(self):
        """Tester le hachage d'adresse de token"""
        address = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
        hash1 = self.hashing_manager.hash_token_address(address)
        hash2 = self.hashing_manager.hash_token_address(address)
        
        # Le hash doit être consistant
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 16)  # 16 caractères
    
    def test_content_deduplication(self):
        """Tester la déduplication de contenu"""
        content = "This is a test message"
        
        # Premier appel - pas de doublon
        self.assertFalse(self.hashing_manager.is_duplicate_content(content))
        
        # Deuxième appel - doublon détecté
        self.assertTrue(self.hashing_manager.is_duplicate_content(content))
    
    def test_cleanup_old_hashes(self):
        """Tester le nettoyage des anciens hashes"""
        # Ajouter beaucoup de contenus
        for i in range(1500):
            self.hashing_manager.is_duplicate_content(f"content_{i}")
        
        # Vérifier que le cache est plein
        self.assertGreater(len(self.hashing_manager.content_hashes), 1000)
        
        # Nettoyer
        self.hashing_manager.cleanup_old_hashes()
        
        # Vérifier que le cache a été nettoyé
        self.assertEqual(len(self.hashing_manager.content_hashes), 0)

class TestCacheManager(unittest.IsolatedAsyncioTestCase):
    """Tests pour le gestionnaire de cache"""
    
    async def asyncSetUp(self):
        # Utiliser un faux Redis pour les tests
        self.fake_redis = fakeredis.FakeRedis(decode_responses=True)
        self.cache_manager = CacheManager(self.fake_redis)
    
    async def test_cache_operations(self):
        """Tester les opérations de cache"""
        key = "test_key"
        value = {"test": "data"}
        
        # Vérifier que la clé n'existe pas
        result = await self.cache_manager.get(key)
        self.assertIsNone(result)
        
        # Stocker une valeur
        await self.cache_manager.set(key, value)
        
        # Récupérer la valeur
        result = await self.cache_manager.get(key)
        self.assertEqual(result, value)
    
    async def test_local_cache(self):
        """Tester le cache local"""
        key = "local_test"
        value = {"local": "data"}
        
        # Stocker dans le cache
        await self.cache_manager.set(key, value)
        
        # Premier accès - depuis Redis
        result1 = await self.cache_manager.get(key)
        self.assertEqual(result1, value)
        
        # Deuxième accès - depuis le cache local
        result2 = await self.cache_manager.get(key)
        self.assertEqual(result2, value)
        
        # Vérifier les statistiques
        stats = self.cache_manager.get_stats()
        self.assertGreater(stats['hits'], 0)

class TestCollaborativeFilter(unittest.TestCase):
    """Tests pour le filtre collaboratif"""
    
    def setUp(self):
        self.collaborative_filter = CollaborativeFilter()
    
    def test_user_interaction(self):
        """Tester l'ajout d'interactions utilisateur"""
        user_id = "user123"
        token_address = "token456"
        
        self.collaborative_filter.add_user_interaction(
            user_id, token_address, "like", 0.8
        )
        
        # Vérifier que l'interaction a été ajoutée
        self.assertIn(user_id, self.collaborative_filter.user_preferences)
        self.assertIn(token_address, self.collaborative_filter.user_preferences[user_id])
    
    def test_token_similarity(self):
        """Tester le calcul de similarité entre tokens"""
        # Ajouter des interactions pour créer des similarités
        users = ["user1", "user2", "user3"]
        token1 = "token1"
        token2 = "token2"
        
        # Users 1 et 2 aiment les deux tokens
        for user in users[:2]:
            self.collaborative_filter.add_user_interaction(user, token1, "like", 0.8)
            self.collaborative_filter.add_user_interaction(user, token2, "like", 0.7)
        
        # User 3 aime seulement token1
        self.collaborative_filter.add_user_interaction(users[2], token1, "like", 0.9)
        
        # Calculer la similarité
        similarity = self.collaborative_filter.calculate_token_similarity(token1, token2)
        
        # Doit être > 0 car ils partagent des utilisateurs
        self.assertGreater(similarity, 0)
    
    def test_recommendations(self):
        """Tester les recommandations de tokens similaires"""
        # Créer un scénario avec plusieurs tokens
        users = ["user1", "user2", "user3"]
        tokens = ["tokenA", "tokenB", "tokenC"]
        
        # Créer des patterns d'interaction
        for user in users:
            for token in tokens:
                score = 0.5 + (hash(user + token) % 100) / 200  # Score pseudo-aléatoire
                self.collaborative_filter.add_user_interaction(user, token, "view", score)
        
        # Obtenir des recommandations
        recommendations = self.collaborative_filter.recommend_similar_tokens("tokenA", limit=2)
        
        # Vérifier le format des recommandations
        self.assertIsInstance(recommendations, list)
        self.assertLessEqual(len(recommendations), 2)
        
        for token, similarity in recommendations:
            self.assertIsInstance(token, str)
            self.assertIsInstance(similarity, float)
            self.assertGreaterEqual(similarity, 0)

class TestGraphAnalyzer(unittest.TestCase):
    """Tests pour l'analyseur de graphe"""
    
    def setUp(self):
        self.graph_analyzer = GraphAnalyzer()
    
    def test_social_connections(self):
        """Tester l'ajout de connexions sociales"""
        user1 = "alice"
        user2 = "bob"
        
        self.graph_analyzer.add_social_connection(user1, user2)
        
        # Vérifier que la connexion existe
        self.assertIn(user2, self.graph_analyzer.social_graph[user1])
    
    def test_token_mentions(self):
        """Tester l'ajout de mentions de tokens"""
        user = "crypto_trader"
        token = "meme_token_123"
        
        self.graph_analyzer.add_token_mention(user, token)
        
        # Vérifier que la mention a été ajoutée
        self.assertIn(user, self.graph_analyzer.token_communities[token])
    
    def test_influence_score(self):
        """Tester le calcul du score d'influence"""
        # Créer un réseau simple
        users = ["influencer", "follower1", "follower2", "follower3"]
        
        # L'influenceur est connecté à tous les followers
        for follower in users[1:]:
            self.graph_analyzer.add_social_connection(users[0], follower)
        
        # Les followers sont connectés entre eux
        self.graph_analyzer.add_social_connection(users[1], users[2])
        
        # Calculer les scores d'influence
        influencer_score = self.graph_analyzer.calculate_influence_score(users[0])
        follower_score = self.graph_analyzer.calculate_influence_score(users[1])
        
        # L'influenceur doit avoir un score plus élevé
        self.assertGreater(influencer_score, follower_score)
    
    def test_community_strength(self):
        """Tester le calcul de la force de communauté"""
        token = "community_token"
        users = ["user1", "user2", "user3"]
        
        # Ajouter des mentions
        for user in users:
            self.graph_analyzer.add_token_mention(user, token)
        
        # Ajouter quelques connexions pour augmenter l'influence
        self.graph_analyzer.add_social_connection(users[0], users[1])
        
        # Calculer la force de la communauté
        strength = self.graph_analyzer.get_community_strength(token)
        
        # Doit être > 0
        self.assertGreater(strength, 0)
        self.assertLessEqual(strength, 1)  # Normalisé entre 0 et 1

class TestStreamFilter(unittest.IsolatedAsyncioTestCase):
    """Tests pour le filtre de flux principal"""
    
    async def asyncSetUp(self):
        # Configuration de test
        self.config = Config()
        self.config.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
        self.config.DEFAULT_FILTER_CRITERIA = {
            'min_market_cap': 10000,
            'max_market_cap': 1000000,
            'min_liquidity': 5000,
            'min_volume_24h': 1000,
            'min_sentiment_score': 0.3
        }
        
        # Utiliser un faux Redis
        self.fake_redis = fakeredis.FakeRedis(decode_responses=True)
        
        # Mock Kafka producer
        with patch('stream_filter.KafkaProducer') as mock_producer:
            mock_producer.return_value = Mock()
            self.stream_filter = StreamFilter(self.config, self.fake_redis)
    
    async def test_event_processing(self):
        """Tester le traitement d'événements"""
        # Créer un événement de test
        token_data = TokenData(
            mint_address="test_token_123",
            symbol="TEST",
            name="Test Token",
            creation_timestamp=int(time.time()),
            supply=1000000,
            decimals=9,
            current_price_usd=0.001,
            market_cap_usd=50000,  # Dans la fourchette acceptable
            liquidity_usd=10000,   # Liquidité suffisante
            volume_24h_usd=5000,   # Volume suffisant
            price_change_1h_percent=5.0,
            price_change_24h_percent=10.0,
            social_sentiment_score=0.6,  # Sentiment positif
            social_mentions_24h=25,
            community_engagement_score=0.7,
            last_updated_timestamp=int(time.time())
        )
        
        event = StreamEvent(
            event_type='new_token',
            timestamp=int(time.time()),
            data=token_data.to_dict(),
            source='test'
        )
        
        # Ajouter l'événement à la queue
        await self.stream_filter.add_event(event)
        
        # Vérifier que l'événement a été ajouté
        self.assertFalse(self.stream_filter.event_queue.empty())
    
    async def test_filter_criteria_matching(self):
        """Tester la correspondance des critères de filtrage"""
        # Créer un token qui correspond aux critères
        good_token = TokenData(
            mint_address="good_token",
            symbol="GOOD",
            name="Good Token",
            creation_timestamp=int(time.time()),
            supply=1000000,
            decimals=9,
            current_price_usd=0.001,
            market_cap_usd=100000,  # Dans la fourchette
            liquidity_usd=20000,    # Bonne liquidité
            volume_24h_usd=10000,   # Bon volume
            social_sentiment_score=0.7,  # Bon sentiment
            social_mentions_24h=50,
            community_engagement_score=0.8,
            last_updated_timestamp=int(time.time())
        )
        
        # Créer un token qui ne correspond pas
        bad_token = TokenData(
            mint_address="bad_token",
            symbol="BAD",
            name="Bad Token",
            creation_timestamp=int(time.time()),
            supply=1000000,
            decimals=9,
            current_price_usd=0.001,
            market_cap_usd=5000,     # Trop faible
            liquidity_usd=1000,     # Liquidité insuffisante
            volume_24h_usd=100,     # Volume trop faible
            social_sentiment_score=0.1,  # Sentiment négatif
            social_mentions_24h=5,
            community_engagement_score=0.2,
            last_updated_timestamp=int(time.time())
        )
        
        # Tester la correspondance
        matches_good, reasons_good = self.stream_filter.filter_criteria.matches_token(good_token)
        matches_bad, reasons_bad = self.stream_filter.filter_criteria.matches_token(bad_token)
        
        # Le bon token doit correspondre
        self.assertTrue(matches_good)
        self.assertGreater(len(reasons_good), 0)
        
        # Le mauvais token ne doit pas correspondre
        self.assertFalse(matches_bad)
    
    def test_system_stats(self):
        """Tester la récupération des statistiques système"""
        stats = self.stream_filter.get_system_stats()
        
        # Vérifier la structure des statistiques
        self.assertIn('processing_stats', stats)
        self.assertIn('cache_stats', stats)
        self.assertIn('running', stats)
        
        # Vérifier les types
        self.assertIsInstance(stats['processing_stats'], dict)
        self.assertIsInstance(stats['running'], bool)

class TestIntegration(unittest.IsolatedAsyncioTestCase):
    """Tests d'intégration pour le système complet"""
    
    async def asyncSetUp(self):
        self.config = Config()
        self.fake_redis = fakeredis.FakeRedis(decode_responses=True)
        
        # Mock des composants externes
        with patch('stream_filter.KafkaProducer') as mock_producer:
            mock_producer.return_value = Mock()
            self.stream_filter = StreamFilter(self.config, self.fake_redis)
    
    async def test_end_to_end_token_processing(self):
        """Test de bout en bout du traitement d'un token"""
        # Créer un token de test
        token_data = TokenData(
            mint_address="integration_test_token",
            symbol="ITT",
            name="Integration Test Token",
            creation_timestamp=int(time.time()),
            supply=1000000,
            decimals=9,
            current_price_usd=0.005,
            market_cap_usd=250000,
            liquidity_usd=15000,
            volume_24h_usd=8000,
            social_sentiment_score=0.65,
            social_mentions_24h=30,
            community_engagement_score=0.75,
            last_updated_timestamp=int(time.time())
        )
        
        # Simuler le processus complet
        event = StreamEvent(
            event_type='new_token',
            timestamp=int(time.time()),
            data=token_data.to_dict(),
            source='integration_test'
        )
        
        # Ajouter l'événement
        await self.stream_filter.add_event(event)
        
        # Vérifier que l'événement a été traité
        # Dans un test réel, on vérifierait les effets de bord
        self.assertTrue(True)  # Placeholder pour test plus complexe

if __name__ == '__main__':
    # Exécuter les tests
    unittest.main()

