"""
Module d'analyse de sentiment en temps réel
Utilise des APIs externes et des modèles NLP pour analyser le sentiment des réseaux sociaux
"""
import asyncio
import aiohttp
import logging
import re
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import json
from collections import defaultdict, deque

from config import Config

@dataclass
class SentimentResult:
    """Résultat d'analyse de sentiment"""
    score: float  # -1.0 (très négatif) à 1.0 (très positif)
    confidence: float  # 0.0 à 1.0
    emotions: Dict[str, float]  # {'joy': 0.8, 'fear': 0.1, etc.}
    keywords: List[str]
    processing_time_ms: float

class SentimentAnalyzer:
    """Analyseur de sentiment en temps réel"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.session = None
        
        # Cache pour éviter les analyses répétées
        self.sentiment_cache = {}
        self.cache_ttl = 300  # 5 minutes
        
        # Statistiques
        self.stats = {
            'analyses_performed': 0,
            'cache_hits': 0,
            'api_calls': 0,
            'average_processing_time': 0.0
        }
        
        # Mots-clés crypto et meme coins
        self.crypto_keywords = {
            'positive': ['moon', 'bullish', 'pump', 'gem', 'diamond', 'hodl', 'buy', 'rocket', '🚀', '💎', '🌙'],
            'negative': ['dump', 'bearish', 'crash', 'scam', 'rug', 'sell', 'dead', 'rip', '💀', '📉'],
            'neutral': ['hold', 'dip', 'consolidation', 'sideways', 'analysis', 'chart']
        }
        
        # Patterns pour détecter les mentions de prix/performance
        self.price_patterns = [
            r'(\+|\-)\d+(\.\d+)?%',  # +10%, -5.5%
            r'\d+x',  # 10x, 100x
            r'(\$\d+(\.\d+)?)',  # $1.50, $0.001
            r'(up|down)\s+\d+%'  # up 20%, down 15%
        ]
    
    async def __aenter__(self):
        """Gestionnaire de contexte asynchrone - entrée"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Gestionnaire de contexte asynchrone - sortie"""
        if self.session:
            await self.session.close()
    
    async def analyze_sentiment(self, text: str, context: str = 'general') -> SentimentResult:
        """Analyser le sentiment d'un texte"""
        start_time = time.time()
        
        try:
            # Vérifier le cache
            cache_key = self._get_cache_key(text)
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
            
            # Préprocesser le texte
            cleaned_text = self._preprocess_text(text)
            
            # Analyser avec plusieurs méthodes et combiner les résultats
            results = []
            
            # 1. Analyse basée sur les mots-clés crypto
            keyword_result = await self._analyze_with_crypto_keywords(cleaned_text)
            results.append(keyword_result)
            
            # 2. Analyse avec API externe (si disponible)
            api_result = await self._analyze_with_external_api(cleaned_text)
            if api_result:
                results.append(api_result)
            
            # 3. Analyse des patterns de prix
            price_sentiment = await self._analyze_price_patterns(cleaned_text)
            if price_sentiment:
                results.append(price_sentiment)
            
            # Combiner les résultats
            final_result = self._combine_sentiment_results(results, text)
            
            # Calculer le temps de traitement
            processing_time = (time.time() - start_time) * 1000
            final_result.processing_time_ms = processing_time
            
            # Mettre en cache
            self._cache_result(cache_key, final_result)
            
            # Mettre à jour les statistiques
            self.stats['analyses_performed'] += 1
            self._update_average_processing_time(processing_time)
            
            return final_result
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'analyse de sentiment: {e}")
            return SentimentResult(
                score=0.0,
                confidence=0.0,
                emotions={},
                keywords=[],
                processing_time_ms=(time.time() - start_time) * 1000
            )
    
    def _preprocess_text(self, text: str) -> str:
        """Préprocesser le texte pour l'analyse"""
        # Convertir en minuscules
        text = text.lower()
        
        # Supprimer les URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # Supprimer les mentions (@username)
        text = re.sub(r'@\w+', '', text)
        
        # Supprimer les hashtags mais garder le contenu
        text = re.sub(r'#(\w+)', r'\1', text)
        
        # Nettoyer les espaces multiples
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    async def _analyze_with_crypto_keywords(self, text: str) -> SentimentResult:
        """Analyser le sentiment basé sur les mots-clés crypto"""
        positive_score = 0
        negative_score = 0
        found_keywords = []
        
        words = text.split()
        
        # Compter les mots-clés positifs
        for keyword in self.crypto_keywords['positive']:
            count = text.count(keyword)
            if count > 0:
                positive_score += count
                found_keywords.extend([keyword] * count)
        
        # Compter les mots-clés négatifs
        for keyword in self.crypto_keywords['negative']:
            count = text.count(keyword)
            if count > 0:
                negative_score += count
                found_keywords.extend([keyword] * count)
        
        # Calculer le score final
        total_keywords = positive_score + negative_score
        if total_keywords == 0:
            sentiment_score = 0.0
            confidence = 0.1
        else:
            sentiment_score = (positive_score - negative_score) / total_keywords
            confidence = min(total_keywords / 10, 1.0)  # Plus de mots-clés = plus de confiance
        
        # Émotions basiques
        emotions = {}
        if sentiment_score > 0.3:
            emotions['joy'] = min(sentiment_score, 1.0)
            emotions['excitement'] = min(sentiment_score * 0.8, 1.0)
        elif sentiment_score < -0.3:
            emotions['fear'] = min(abs(sentiment_score), 1.0)
            emotions['anger'] = min(abs(sentiment_score) * 0.6, 1.0)
        else:
            emotions['neutral'] = 0.8
        
        return SentimentResult(
            score=sentiment_score,
            confidence=confidence,
            emotions=emotions,
            keywords=list(set(found_keywords)),
            processing_time_ms=0.0
        )
    
    async def _analyze_with_external_api(self, text: str) -> Optional[SentimentResult]:
        """Analyser avec une API externe (Google Cloud, AWS, etc.)"""
        try:
            # Exemple avec une API de sentiment générique
            # Dans une implémentation réelle, utiliser Google Cloud Natural Language, AWS Comprehend, etc.
            
            # Simulation d'appel API
            if len(text) < 10:  # Texte trop court
                return None
            
            # Simuler un appel API (remplacer par un vrai appel)
            api_result = await self._simulate_api_call(text)
            
            if api_result:
                self.stats['api_calls'] += 1
                return api_result
            
        except Exception as e:
            self.logger.error(f"Erreur API externe: {e}")
        
        return None
    
    async def _simulate_api_call(self, text: str) -> Optional[SentimentResult]:
        """Simuler un appel API pour la démonstration"""
        # Cette fonction simule une réponse d'API de sentiment
        # Dans un environnement de production, remplacer par de vrais appels API
        
        await asyncio.sleep(0.1)  # Simuler la latence réseau
        
        # Analyse simple basée sur la longueur et le contenu
        word_count = len(text.split())
        
        # Score basé sur des heuristiques simples
        if 'good' in text or 'great' in text or 'awesome' in text:
            score = 0.7
        elif 'bad' in text or 'terrible' in text or 'awful' in text:
            score = -0.7
        else:
            score = 0.0
        
        confidence = min(word_count / 20, 0.9)
        
        return SentimentResult(
            score=score,
            confidence=confidence,
            emotions={'simulated': abs(score)},
            keywords=[],
            processing_time_ms=0.0
        )
    
    async def _analyze_price_patterns(self, text: str) -> Optional[SentimentResult]:
        """Analyser les patterns de prix pour déterminer le sentiment"""
        price_indicators = []
        
        for pattern in self.price_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            price_indicators.extend(matches)
        
        if not price_indicators:
            return None
        
        # Analyser les indicateurs de prix
        positive_indicators = 0
        negative_indicators = 0
        
        for indicator in price_indicators:
            indicator_str = str(indicator).lower()
            
            if '+' in indicator_str or 'up' in indicator_str or 'x' in indicator_str:
                positive_indicators += 1
            elif '-' in indicator_str or 'down' in indicator_str:
                negative_indicators += 1
        
        total_indicators = positive_indicators + negative_indicators
        if total_indicators == 0:
            return None
        
        score = (positive_indicators - negative_indicators) / total_indicators
        confidence = min(total_indicators / 5, 0.8)
        
        return SentimentResult(
            score=score,
            confidence=confidence,
            emotions={'price_optimism' if score > 0 else 'price_pessimism': abs(score)},
            keywords=[str(ind) for ind in price_indicators],
            processing_time_ms=0.0
        )
    
    def _combine_sentiment_results(self, results: List[SentimentResult], original_text: str) -> SentimentResult:
        """Combiner plusieurs résultats d'analyse de sentiment"""
        if not results:
            return SentimentResult(0.0, 0.0, {}, [], 0.0)
        
        # Calculer la moyenne pondérée par la confiance
        total_weighted_score = 0.0
        total_confidence = 0.0
        all_emotions = defaultdict(float)
        all_keywords = []
        
        for result in results:
            weight = result.confidence
            total_weighted_score += result.score * weight
            total_confidence += weight
            
            # Combiner les émotions
            for emotion, value in result.emotions.items():
                all_emotions[emotion] += value * weight
            
            all_keywords.extend(result.keywords)
        
        # Score final
        final_score = total_weighted_score / total_confidence if total_confidence > 0 else 0.0
        final_confidence = total_confidence / len(results)
        
        # Normaliser les émotions
        if total_confidence > 0:
            for emotion in all_emotions:
                all_emotions[emotion] /= total_confidence
        
        # Ajustement contextuel pour les meme coins
        final_score = self._apply_meme_coin_context(final_score, original_text)
        
        return SentimentResult(
            score=max(-1.0, min(1.0, final_score)),  # Limiter entre -1 et 1
            confidence=min(final_confidence, 1.0),
            emotions=dict(all_emotions),
            keywords=list(set(all_keywords)),
            processing_time_ms=0.0
        )
    
    def _apply_meme_coin_context(self, score: float, text: str) -> float:
        """Appliquer un ajustement contextuel pour les meme coins"""
        # Les meme coins ont tendance à avoir des sentiments plus extrêmes
        meme_indicators = ['meme', 'doge', 'shib', 'pepe', 'wojak', 'chad']
        
        has_meme_context = any(indicator in text.lower() for indicator in meme_indicators)
        
        if has_meme_context:
            # Amplifier légèrement le sentiment pour les meme coins
            if score > 0:
                score = min(score * 1.2, 1.0)
            elif score < 0:
                score = max(score * 1.2, -1.0)
        
        return score
    
    def _get_cache_key(self, text: str) -> str:
        """Générer une clé de cache pour le texte"""
        import hashlib
        return hashlib.md5(text.encode()).hexdigest()
    
    def _get_from_cache(self, cache_key: str) -> Optional[SentimentResult]:
        """Récupérer un résultat du cache"""
        if cache_key in self.sentiment_cache:
            entry = self.sentiment_cache[cache_key]
            if time.time() - entry['timestamp'] < self.cache_ttl:
                return entry['result']
            else:
                del self.sentiment_cache[cache_key]
        return None
    
    def _cache_result(self, cache_key: str, result: SentimentResult):
        """Mettre en cache un résultat"""
        self.sentiment_cache[cache_key] = {
            'result': result,
            'timestamp': time.time()
        }
        
        # Nettoyer le cache si trop grand
        if len(self.sentiment_cache) > 1000:
            self._cleanup_cache()
    
    def _cleanup_cache(self):
        """Nettoyer les anciennes entrées du cache"""
        current_time = time.time()
        keys_to_remove = []
        
        for key, entry in self.sentiment_cache.items():
            if current_time - entry['timestamp'] > self.cache_ttl:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.sentiment_cache[key]
    
    def _update_average_processing_time(self, processing_time: float):
        """Mettre à jour le temps de traitement moyen"""
        current_avg = self.stats['average_processing_time']
        count = self.stats['analyses_performed']
        
        if count == 1:
            self.stats['average_processing_time'] = processing_time
        else:
            self.stats['average_processing_time'] = (current_avg * (count - 1) + processing_time) / count
    
    async def analyze_batch_sentiment(self, texts: List[str]) -> List[SentimentResult]:
        """Analyser le sentiment d'un lot de textes"""
        tasks = [self.analyze_sentiment(text) for text in texts]
        return await asyncio.gather(*tasks)
    
    async def get_aggregated_sentiment(self, texts: List[str]) -> Dict[str, float]:
        """Obtenir le sentiment agrégé d'une liste de textes"""
        results = await self.analyze_batch_sentiment(texts)
        
        if not results:
            return {'score': 0.0, 'confidence': 0.0, 'count': 0}
        
        # Calculer les moyennes
        total_score = sum(r.score * r.confidence for r in results)
        total_confidence = sum(r.confidence for r in results)
        
        avg_score = total_score / total_confidence if total_confidence > 0 else 0.0
        avg_confidence = total_confidence / len(results)
        
        # Distribution des sentiments
        positive_count = sum(1 for r in results if r.score > 0.1)
        negative_count = sum(1 for r in results if r.score < -0.1)
        neutral_count = len(results) - positive_count - negative_count
        
        return {
            'score': avg_score,
            'confidence': avg_confidence,
            'count': len(results),
            'positive_count': positive_count,
            'negative_count': negative_count,
            'neutral_count': neutral_count,
            'positive_ratio': positive_count / len(results),
            'negative_ratio': negative_count / len(results),
            'neutral_ratio': neutral_count / len(results)
        }
    
    def get_stats(self) -> Dict[str, float]:
        """Obtenir les statistiques de l'analyseur"""
        return {
            **self.stats,
            'cache_size': len(self.sentiment_cache),
            'cache_hit_rate': (self.stats['cache_hits'] / max(self.stats['analyses_performed'], 1)) * 100
        }
    
    async def detect_sentiment_trends(self, historical_data: List[Tuple[int, str]]) -> Dict[str, Any]:
        """Détecter les tendances de sentiment dans des données historiques"""
        if not historical_data:
            return {'trend': 'unknown', 'strength': 0.0}
        
        # Trier par timestamp
        sorted_data = sorted(historical_data, key=lambda x: x[0])
        
        # Analyser le sentiment de chaque texte
        texts = [item[1] for item in sorted_data]
        timestamps = [item[0] for item in sorted_data]
        
        sentiment_results = await self.analyze_batch_sentiment(texts)
        
        # Calculer la tendance
        scores = [r.score for r in sentiment_results]
        
        if len(scores) < 2:
            return {'trend': 'insufficient_data', 'strength': 0.0}
        
        # Tendance simple: comparer première et dernière moitié
        mid_point = len(scores) // 2
        first_half_avg = sum(scores[:mid_point]) / mid_point
        second_half_avg = sum(scores[mid_point:]) / (len(scores) - mid_point)
        
        trend_strength = second_half_avg - first_half_avg
        
        if trend_strength > 0.1:
            trend = 'improving'
        elif trend_strength < -0.1:
            trend = 'declining'
        else:
            trend = 'stable'
        
        return {
            'trend': trend,
            'strength': abs(trend_strength),
            'first_half_sentiment': first_half_avg,
            'second_half_sentiment': second_half_avg,
            'data_points': len(scores)
        }

