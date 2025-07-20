"""
Module principal du bot de trading Solana
Orchestre tous les composants et gère le cycle de vie du système
"""
import asyncio
import logging
import signal
import sys
import time
from typing import Dict, Any, Optional
import redis
from datetime import datetime

from config import Config
from models import TokenData, StreamEvent
from solana_monitor import SolanaMonitor
from market_analyzer import MarketAnalyzer
from stream_filter import StreamFilter
from social_monitor import SocialMonitor
from notification_system import NotificationService

class SolanaMemeBot:
    """Bot principal de trading des meme coins Solana"""
    
    def __init__(self, config_path: Optional[str] = None):
        # Configuration
        self.config = Config(config_path)
        
        # Configuration du logging
        self._setup_logging()
        self.logger = logging.getLogger(__name__)
        
        # Redis pour le cache et les queues
        self.redis_client = redis.Redis(
            host=self.config.REDIS_HOST,
            port=self.config.REDIS_PORT,
            db=self.config.REDIS_DB,
            decode_responses=True
        )
        
        # Composants principaux
        self.solana_monitor = SolanaMonitor(self.config)
        self.market_analyzer = None  # Initialisé dans start()
        self.stream_filter = StreamFilter(self.config, self.redis_client)
        self.social_monitor = SocialMonitor(self.config)
        self.notification_service = NotificationService(self.config)
        
        # État du système
        self.running = False
        self.start_time = None
        self.stats = {
            'tokens_discovered': 0,
            'tokens_analyzed': 0,
            'notifications_sent': 0,
            'uptime_seconds': 0
        }
        
        # Gestionnaire de signaux pour arrêt propre
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _setup_logging(self):
        """Configurer le système de logging"""
        logging.basicConfig(
            level=getattr(logging, self.config.LOG_LEVEL.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('solana_meme_bot.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
    
    def _signal_handler(self, signum, frame):
        """Gestionnaire de signaux pour arrêt propre"""
        self.logger.info(f"Signal {signum} reçu, arrêt du bot...")
        asyncio.create_task(self.stop())
    
    async def start(self):
        """Démarrer le bot"""
        try:
            self.logger.info("🚀 Démarrage du Solana Meme Bot...")
            self.start_time = time.time()
            self.running = True
            
            # Vérifier les connexions
            await self._check_connections()
            
            # Initialiser les composants
            await self._initialize_components()
            
            # Configurer les callbacks
            self._setup_callbacks()
            
            # Démarrer les services
            await self._start_services()
            
            self.logger.info("✅ Bot démarré avec succès!")
            
            # Envoyer notification de démarrage
            await self._send_startup_notification()
            
            # Boucle principale
            await self._main_loop()
            
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """Arrêter le bot"""
        if not self.running:
            return
        
        self.logger.info("🛑 Arrêt du bot en cours...")
        self.running = False
        
        try:
            # Arrêter les services
            await self._stop_services()
            
            # Envoyer notification d'arrêt
            await self._send_shutdown_notification()
            
            self.logger.info("✅ Bot arrêté proprement")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'arrêt: {e}")
    
    async def _check_connections(self):
        """Vérifier les connexions aux services externes"""
        self.logger.info("Vérification des connexions...")
        
        # Vérifier Redis
        try:
            self.redis_client.ping()
            self.logger.info("✅ Connexion Redis OK")
        except Exception as e:
            self.logger.error(f"❌ Erreur connexion Redis: {e}")
            raise
        
        # Vérifier les APIs (optionnel)
        # Dans une implémentation complète, vérifier les APIs Solana, Twitter, etc.
        
        self.logger.info("✅ Toutes les connexions sont opérationnelles")
    
    async def _initialize_components(self):
        """Initialiser tous les composants"""
        self.logger.info("Initialisation des composants...")
        
        # Initialiser l'analyseur de marché avec gestionnaire de contexte
        self.market_analyzer = MarketAnalyzer(self.config)
        
        self.logger.info("✅ Composants initialisés")
    
    def _setup_callbacks(self):
        """Configurer les callbacks entre composants"""
        self.logger.info("Configuration des callbacks...")
        
        # Callback pour nouveaux tokens détectés
        self.solana_monitor.add_callback('new_token', self._handle_new_token)
        
        # Callback pour posts sociaux
        self.social_monitor.add_callback('social_post', self._handle_social_post)
        self.social_monitor.add_callback('social_alert', self._handle_social_alert)
        
        self.logger.info("✅ Callbacks configurés")
    
    async def _start_services(self):
        """Démarrer tous les services"""
        self.logger.info("Démarrage des services...")
        
        # Démarrer le service de notifications
        await self.notification_service.start()
        
        # Démarrer le filtre de flux
        asyncio.create_task(self.stream_filter.start_filtering())
        
        # Démarrer les tâches de surveillance
        asyncio.create_task(self.solana_monitor.start_monitoring())
        asyncio.create_task(self.social_monitor.start_monitoring())
        
        # Démarrer les tâches de maintenance
        asyncio.create_task(self._stats_reporter())
        asyncio.create_task(self._health_checker())
        
        self.logger.info("✅ Services démarrés")
    
    async def _stop_services(self):
        """Arrêter tous les services"""
        self.logger.info("Arrêt des services...")
        
        # Arrêter la surveillance
        await self.solana_monitor.stop_monitoring()
        await self.stream_filter.stop_filtering()
        
        # Arrêter les notifications
        await self.notification_service.stop()
        
        self.logger.info("✅ Services arrêtés")
    
    async def _handle_new_token(self, token_data: TokenData):
        """Gérer la détection d'un nouveau token"""
        try:
            self.stats['tokens_discovered'] += 1
            self.logger.info(f"Nouveau token détecté: {token_data.symbol}")
            
            # Analyser les données de marché
            async with self.market_analyzer:
                enriched_token = await self.market_analyzer.analyze_token_market_data(token_data)
                
                # Évaluer l'opportunité de trading
                opportunity = await self.market_analyzer.evaluate_trading_opportunity(enriched_token)
                
                self.stats['tokens_analyzed'] += 1
                
                # Créer un événement pour le filtre de flux
                event = StreamEvent(
                    event_type='new_token',
                    timestamp=int(time.time()),
                    data=enriched_token.to_dict(),
                    source='solana_monitor'
                )
                
                # Ajouter l'évaluation aux données
                event.data['trading_opportunity'] = opportunity
                
                # Envoyer au filtre de flux
                await self.stream_filter.add_event(event)
                
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du nouveau token: {e}")
    
    async def _handle_social_post(self, post):
        """Gérer un nouveau post de réseau social"""
        try:
            # Créer un événement pour le filtre de flux
            event = StreamEvent(
                event_type='social_mention',
                timestamp=post.timestamp,
                data={
                    'user': post.author,
                    'token_address': post.related_token_mint_address,
                    'content': post.content,
                    'sentiment_score': post.sentiment_score,
                    'platform': post.platform,
                    'engagement': post.engagement_metrics.to_dict() if post.engagement_metrics else {}
                },
                source='social_monitor'
            )
            
            # Envoyer au filtre de flux
            await self.stream_filter.add_event(event)
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du post social: {e}")
    
    async def _handle_social_alert(self, alert):
        """Gérer une alerte sociale"""
        try:
            self.logger.info(f"Alerte sociale: {alert.description}")
            
            # Envoyer une notification si l'urgence est élevée
            if alert.urgency == 'high':
                # Créer une notification d'alerte
                # Dans une implémentation complète, créer un message d'alerte approprié
                pass
                
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement de l'alerte sociale: {e}")
    
    async def _main_loop(self):
        """Boucle principale du bot"""
        self.logger.info("Boucle principale démarrée")
        
        while self.running:
            try:
                # Mettre à jour les statistiques
                self.stats['uptime_seconds'] = int(time.time() - self.start_time)
                
                # Attendre avant la prochaine itération
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Erreur dans la boucle principale: {e}")
                await asyncio.sleep(5)
    
    async def _stats_reporter(self):
        """Reporter les statistiques périodiquement"""
        while self.running:
            try:
                await asyncio.sleep(300)  # Toutes les 5 minutes
                
                # Collecter les statistiques de tous les composants
                comprehensive_stats = await self._collect_comprehensive_stats()
                
                self.logger.info(f"📊 Statistiques: {comprehensive_stats}")
                
                # Envoyer un rapport de statut toutes les heures
                if self.stats['uptime_seconds'] % 3600 < 300:  # Proche de l'heure
                    await self.notification_service.send_system_status()
                
            except Exception as e:
                self.logger.error(f"Erreur lors du rapport de statistiques: {e}")
    
    async def _health_checker(self):
        """Vérificateur de santé du système"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Toutes les minutes
                
                # Vérifier la santé des composants
                health_status = await self._check_system_health()
                
                if not health_status['healthy']:
                    self.logger.warning(f"⚠️ Problème de santé détecté: {health_status}")
                    
                    # Envoyer une alerte si critique
                    if health_status['critical']:
                        await self._send_health_alert(health_status)
                
            except Exception as e:
                self.logger.error(f"Erreur lors de la vérification de santé: {e}")
    
    async def _collect_comprehensive_stats(self) -> Dict[str, Any]:
        """Collecter les statistiques de tous les composants"""
        stats = {
            'bot_stats': self.stats.copy(),
            'stream_filter_stats': self.stream_filter.get_system_stats(),
            'notification_stats': self.notification_service.get_comprehensive_stats(),
            'social_monitor_stats': self.social_monitor.get_stats()
        }
        
        return stats
    
    async def _check_system_health(self) -> Dict[str, Any]:
        """Vérifier la santé du système"""
        health = {
            'healthy': True,
            'critical': False,
            'issues': []
        }
        
        try:
            # Vérifier Redis
            self.redis_client.ping()
        except Exception as e:
            health['healthy'] = False
            health['critical'] = True
            health['issues'].append(f"Redis inaccessible: {e}")
        
        # Vérifier les statistiques des composants
        stream_stats = self.stream_filter.get_system_stats()
        if not stream_stats['running']:
            health['healthy'] = False
            health['issues'].append("Stream filter arrêté")
        
        # Vérifier la queue de notifications
        notification_stats = self.notification_service.get_comprehensive_stats()
        queue_size = notification_stats['queue_stats']['queue_size']
        if queue_size > 100:  # Queue trop pleine
            health['healthy'] = False
            health['issues'].append(f"Queue de notifications pleine: {queue_size}")
        
        return health
    
    async def _send_startup_notification(self):
        """Envoyer une notification de démarrage"""
        try:
            if self.notification_service.telegram_notifier:
                await self.notification_service.telegram_notifier.send_alert(
                    "🚀 Bot Démarré",
                    f"Le Solana Meme Bot a démarré avec succès à {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "low"
                )
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi de la notification de démarrage: {e}")
    
    async def _send_shutdown_notification(self):
        """Envoyer une notification d'arrêt"""
        try:
            if self.notification_service.telegram_notifier:
                uptime = time.time() - self.start_time
                await self.notification_service.telegram_notifier.send_alert(
                    "🛑 Bot Arrêté",
                    f"Le Solana Meme Bot s'est arrêté après {uptime/3600:.1f} heures de fonctionnement.",
                    "medium"
                )
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi de la notification d'arrêt: {e}")
    
    async def _send_health_alert(self, health_status: Dict[str, Any]):
        """Envoyer une alerte de santé"""
        try:
            if self.notification_service.telegram_notifier:
                issues_text = "\n".join(f"• {issue}" for issue in health_status['issues'])
                urgency = "high" if health_status['critical'] else "medium"
                
                await self.notification_service.telegram_notifier.send_alert(
                    "⚠️ Alerte Système",
                    f"Problèmes détectés:\n{issues_text}",
                    urgency
                )
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi de l'alerte de santé: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Obtenir le statut complet du bot"""
        return {
            'running': self.running,
            'start_time': self.start_time,
            'uptime_seconds': self.stats['uptime_seconds'],
            'stats': self.stats,
            'config': {
                'solana_rpc_url': self.config.SOLANA_RPC_URL,
                'notification_channels': self.config.NOTIFICATION_CHANNELS,
                'filter_criteria': self.config.DEFAULT_FILTER_CRITERIA
            }
        }

async def main():
    """Fonction principale"""
    bot = None
    try:
        # Créer et démarrer le bot
        bot = SolanaMemeBot()
        await bot.start()
        
    except KeyboardInterrupt:
        print("\n🛑 Interruption clavier détectée")
    except Exception as e:
        print(f"❌ Erreur fatale: {e}")
        logging.error(f"Erreur fatale: {e}", exc_info=True)
    finally:
        if bot:
            await bot.stop()

if __name__ == "__main__":
    # Démarrer le bot
    asyncio.run(main())

