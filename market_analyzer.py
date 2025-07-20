"""
Module d'analyse des données de marché
Responsable de l'évaluation de la capitalisation boursière, liquidité, prix et volume
"""
import asyncio
import aiohttp
import logging
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json

from config import Config
from models import TokenData

class MarketAnalyzer:
    """Analyseur des données de marché pour les tokens Solana"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.session = None
        self.price_cache = {}
        self.liquidity_cache = {}
        
    async def __aenter__(self):
        """Gestionnaire de contexte asynchrone - entrée"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Gestionnaire de contexte asynchrone - sortie"""
        if self.session:
            await self.session.close()
    
    async def analyze_token_market_data(self, token_data: TokenData) -> TokenData:
        """Analyser et mettre à jour les données de marché d'un token"""
        try:
            # Obtenir le prix actuel
            price_data = await self._get_token_price(token_data.mint_address)
            if price_data:
                token_data.current_price_usd = price_data.get('price', 0.0)
                token_data.price_change_1h_percent = price_data.get('price_change_1h', 0.0)
                token_data.price_change_24h_percent = price_data.get('price_change_24h', 0.0)
                token_data.volume_24h_usd = price_data.get('volume_24h', 0.0)
            
            # Calculer la capitalisation boursière
            if token_data.current_price_usd > 0 and token_data.supply > 0:
                token_data.market_cap_usd = (
                    token_data.current_price_usd * 
                    (token_data.supply / (10 ** token_data.decimals))
                )
            
            # Obtenir les données de liquidité
            liquidity_data = await self._get_token_liquidity(token_data.mint_address)
            if liquidity_data:
                token_data.liquidity_usd = liquidity_data.get('total_liquidity', 0.0)
            
            token_data.last_updated_timestamp = int(time.time())
            
            self.logger.info(f"Données de marché mises à jour pour {token_data.symbol}")
            return token_data
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'analyse du marché pour {token_data.mint_address}: {e}")
            return token_data
    
    async def _get_token_price(self, mint_address: str) -> Optional[Dict]:
        """Obtenir les données de prix d'un token"""
        try:
            # Essayer plusieurs sources de données
            price_data = None
            
            # 1. Essayer avec Jupiter API
            price_data = await self._get_price_from_jupiter(mint_address)
            
            # 2. Si Jupiter échoue, essayer avec Birdeye
            if not price_data:
                price_data = await self._get_price_from_birdeye(mint_address)
            
            # 3. Si Birdeye échoue, essayer avec DexScreener
            if not price_data:
                price_data = await self._get_price_from_dexscreener(mint_address)
            
            return price_data
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération du prix pour {mint_address}: {e}")
            return None
    
    async def _get_price_from_jupiter(self, mint_address: str) -> Optional[Dict]:
        """Obtenir le prix via Jupiter API"""
        try:
            url = f"https://price.jup.ag/v4/price?ids={mint_address}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    token_data = data.get('data', {}).get(mint_address)
                    
                    if token_data:
                        return {
                            'price': float(token_data.get('price', 0)),
                            'price_change_1h': 0.0,  # Jupiter ne fournit pas ces données
                            'price_change_24h': 0.0,
                            'volume_24h': 0.0
                        }
                        
        except Exception as e:
            self.logger.debug(f"Erreur Jupiter API pour {mint_address}: {e}")
        
        return None
    
    async def _get_price_from_birdeye(self, mint_address: str) -> Optional[Dict]:
        """Obtenir le prix via Birdeye API"""
        try:
            # API publique de Birdeye (limitée)
            url = f"https://public-api.birdeye.so/defi/price?address={mint_address}"
            headers = {
                'X-API-KEY': 'your-birdeye-api-key'  # Nécessite une clé API
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('success'):
                        price_data = data.get('data', {})
                        return {
                            'price': float(price_data.get('value', 0)),
                            'price_change_1h': float(price_data.get('priceChange1hPercent', 0)),
                            'price_change_24h': float(price_data.get('priceChange24hPercent', 0)),
                            'volume_24h': float(price_data.get('volume24h', 0))
                        }
                        
        except Exception as e:
            self.logger.debug(f"Erreur Birdeye API pour {mint_address}: {e}")
        
        return None
    
    async def _get_price_from_dexscreener(self, mint_address: str) -> Optional[Dict]:
        """Obtenir le prix via DexScreener API"""
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint_address}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    pairs = data.get('pairs', [])
                    
                    if pairs:
                        # Prendre la première paire (généralement la plus liquide)
                        pair = pairs[0]
                        return {
                            'price': float(pair.get('priceUsd', 0)),
                            'price_change_1h': float(pair.get('priceChange', {}).get('h1', 0)),
                            'price_change_24h': float(pair.get('priceChange', {}).get('h24', 0)),
                            'volume_24h': float(pair.get('volume', {}).get('h24', 0))
                        }
                        
        except Exception as e:
            self.logger.debug(f"Erreur DexScreener API pour {mint_address}: {e}")
        
        return None
    
    async def _get_token_liquidity(self, mint_address: str) -> Optional[Dict]:
        """Obtenir les données de liquidité d'un token"""
        try:
            # Obtenir la liquidité depuis plusieurs DEX
            total_liquidity = 0.0
            
            # 1. Raydium
            raydium_liquidity = await self._get_raydium_liquidity(mint_address)
            if raydium_liquidity:
                total_liquidity += raydium_liquidity
            
            # 2. Orca
            orca_liquidity = await self._get_orca_liquidity(mint_address)
            if orca_liquidity:
                total_liquidity += orca_liquidity
            
            return {
                'total_liquidity': total_liquidity,
                'raydium_liquidity': raydium_liquidity or 0.0,
                'orca_liquidity': orca_liquidity or 0.0
            }
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération de la liquidité pour {mint_address}: {e}")
            return None
    
    async def _get_raydium_liquidity(self, mint_address: str) -> Optional[float]:
        """Obtenir la liquidité depuis Raydium"""
        try:
            # API Raydium pour obtenir les pools
            url = f"https://api.raydium.io/v2/sdk/liquidity/mainnet.json"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Chercher les pools contenant notre token
                    for pool in data.get('official', []):
                        if (pool.get('baseMint') == mint_address or 
                            pool.get('quoteMint') == mint_address):
                            
                            # Calculer la liquidité totale du pool
                            base_reserve = float(pool.get('baseReserve', 0))
                            quote_reserve = float(pool.get('quoteReserve', 0))
                            
                            # Estimation simple de la liquidité en USD
                            # Dans une implémentation complète, il faudrait convertir en USD
                            return base_reserve + quote_reserve
                            
        except Exception as e:
            self.logger.debug(f"Erreur Raydium API pour {mint_address}: {e}")
        
        return None
    
    async def _get_orca_liquidity(self, mint_address: str) -> Optional[float]:
        """Obtenir la liquidité depuis Orca"""
        try:
            # API Orca pour obtenir les pools
            url = "https://api.orca.so/v1/whirlpool/list"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Chercher les pools contenant notre token
                    for pool in data.get('whirlpools', []):
                        if (pool.get('tokenA', {}).get('mint') == mint_address or 
                            pool.get('tokenB', {}).get('mint') == mint_address):
                            
                            # Obtenir la liquidité du pool
                            tvl = float(pool.get('tvl', 0))
                            return tvl
                            
        except Exception as e:
            self.logger.debug(f"Erreur Orca API pour {mint_address}: {e}")
        
        return None
    
    async def calculate_market_cap_category(self, market_cap: float) -> str:
        """Catégoriser la capitalisation boursière"""
        if market_cap < 100000:  # < 100k
            return "micro"
        elif market_cap < 1000000:  # < 1M
            return "small"
        elif market_cap < 10000000:  # < 10M
            return "medium"
        elif market_cap < 100000000:  # < 100M
            return "large"
        else:
            return "mega"
    
    async def calculate_liquidity_score(self, liquidity: float) -> float:
        """Calculer un score de liquidité (0-1)"""
        # Score basé sur la liquidité
        if liquidity < 10000:  # < 10k
            return 0.1
        elif liquidity < 50000:  # < 50k
            return 0.3
        elif liquidity < 100000:  # < 100k
            return 0.5
        elif liquidity < 500000:  # < 500k
            return 0.7
        elif liquidity < 1000000:  # < 1M
            return 0.8
        else:
            return 1.0
    
    async def detect_price_trend(self, mint_address: str, timeframe: str = '1h') -> Dict:
        """Détecter la tendance des prix"""
        try:
            # Obtenir l'historique des prix
            price_history = await self._get_price_history(mint_address, timeframe)
            
            if not price_history or len(price_history) < 2:
                return {'trend': 'unknown', 'strength': 0.0}
            
            # Calculer la tendance
            prices = [p['price'] for p in price_history]
            
            # Tendance simple basée sur le premier et dernier prix
            first_price = prices[0]
            last_price = prices[-1]
            
            if last_price > first_price:
                trend = 'bullish'
                strength = (last_price - first_price) / first_price
            elif last_price < first_price:
                trend = 'bearish'
                strength = (first_price - last_price) / first_price
            else:
                trend = 'sideways'
                strength = 0.0
            
            return {
                'trend': trend,
                'strength': min(strength, 1.0),  # Limiter à 1.0
                'price_points': len(prices)
            }
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la détection de tendance pour {mint_address}: {e}")
            return {'trend': 'unknown', 'strength': 0.0}
    
    async def _get_price_history(self, mint_address: str, timeframe: str) -> List[Dict]:
        """Obtenir l'historique des prix"""
        try:
            # Cette fonction devrait obtenir l'historique des prix
            # depuis une API ou une base de données
            # Pour la démonstration, retourner des données simulées
            
            current_time = int(time.time())
            history = []
            
            # Simuler 24 points de données pour la dernière heure
            for i in range(24):
                timestamp = current_time - (i * 150)  # Toutes les 2.5 minutes
                # Prix simulé avec une légère variation
                price = 0.001 * (1 + (i * 0.01))  # Tendance haussière simulée
                
                history.append({
                    'timestamp': timestamp,
                    'price': price
                })
            
            return history[::-1]  # Inverser pour avoir l'ordre chronologique
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération de l'historique pour {mint_address}: {e}")
            return []
    
    async def evaluate_trading_opportunity(self, token_data: TokenData) -> Dict:
        """Évaluer l'opportunité de trading d'un token"""
        try:
            score = 0.0
            factors = {}
            
            # Facteur 1: Capitalisation boursière (poids: 20%)
            market_cap_score = await self._score_market_cap(token_data.market_cap_usd)
            factors['market_cap'] = market_cap_score
            score += market_cap_score * 0.2
            
            # Facteur 2: Liquidité (poids: 25%)
            liquidity_score = await self.calculate_liquidity_score(token_data.liquidity_usd)
            factors['liquidity'] = liquidity_score
            score += liquidity_score * 0.25
            
            # Facteur 3: Tendance des prix (poids: 30%)
            trend_data = await self.detect_price_trend(token_data.mint_address)
            trend_score = await self._score_price_trend(trend_data)
            factors['price_trend'] = trend_score
            score += trend_score * 0.3
            
            # Facteur 4: Volume (poids: 25%)
            volume_score = await self._score_volume(token_data.volume_24h_usd)
            factors['volume'] = volume_score
            score += volume_score * 0.25
            
            return {
                'overall_score': min(score, 1.0),
                'factors': factors,
                'recommendation': await self._get_recommendation(score)
            }
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'évaluation de l'opportunité pour {token_data.mint_address}: {e}")
            return {'overall_score': 0.0, 'factors': {}, 'recommendation': 'avoid'}
    
    async def _score_market_cap(self, market_cap: float) -> float:
        """Scorer la capitalisation boursière"""
        # Score optimal pour les meme coins: entre 50k et 500k
        if 50000 <= market_cap <= 500000:
            return 1.0
        elif 10000 <= market_cap < 50000:
            return 0.7
        elif 500000 < market_cap <= 1000000:
            return 0.6
        elif market_cap < 10000:
            return 0.3
        else:
            return 0.2
    
    async def _score_price_trend(self, trend_data: Dict) -> float:
        """Scorer la tendance des prix"""
        trend = trend_data.get('trend', 'unknown')
        strength = trend_data.get('strength', 0.0)
        
        if trend == 'bullish':
            return min(strength * 2, 1.0)  # Favoriser les tendances haussières
        elif trend == 'sideways':
            return 0.5
        elif trend == 'bearish':
            return max(0.1, 1.0 - strength)
        else:
            return 0.3
    
    async def _score_volume(self, volume: float) -> float:
        """Scorer le volume de transactions"""
        if volume >= 100000:  # >= 100k
            return 1.0
        elif volume >= 50000:  # >= 50k
            return 0.8
        elif volume >= 10000:  # >= 10k
            return 0.6
        elif volume >= 1000:   # >= 1k
            return 0.4
        else:
            return 0.2
    
    async def _get_recommendation(self, score: float) -> str:
        """Obtenir une recommandation basée sur le score"""
        if score >= 0.8:
            return 'strong_buy'
        elif score >= 0.6:
            return 'buy'
        elif score >= 0.4:
            return 'hold'
        elif score >= 0.2:
            return 'weak_sell'
        else:
            return 'avoid'

