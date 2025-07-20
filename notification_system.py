"""
Système de notifications en temps réel
Gère l'envoi de notifications via Telegram et email avec support des queues
"""
import asyncio
import aiohttp
import smtplib
import logging
import time
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from kafka import KafkaConsumer, KafkaProducer
import threading
from queue import Queue
import ssl

from config import Config
from models import NotificationMessage, TokenData

@dataclass
class NotificationConfig:
    """Configuration pour les notifications"""
    telegram_enabled: bool = True
    email_enabled: bool = False
    telegram_chat_id: str = ""
    email_address: str = ""
    email_smtp_server: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    max_notifications_per_hour: int = 50
    notification_cooldown_seconds: int = 300  # 5 minutes entre notifications du même token

class TelegramNotifier:
    """Service de notification Telegram"""
    
    def __init__(self, bot_token: str, config: NotificationConfig):
        self.bot_token = bot_token
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.session = None
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        # Statistiques
        self.stats = {
            'messages_sent': 0,
            'messages_failed': 0,
            'last_message_time': 0
        }
    
    async def __aenter__(self):
        """Gestionnaire de contexte asynchrone - entrée"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Gestionnaire de contexte asynchrone - sortie"""
        if self.session:
            await self.session.close()
    
    async def send_notification(self, message: NotificationMessage) -> bool:
        """Envoyer une notification Telegram"""
        try:
            if not self.config.telegram_enabled or not self.config.telegram_chat_id:
                self.logger.warning("Telegram non configuré")
                return False
            
            # Formater le message
            formatted_message = self._format_telegram_message(message)
            
            # Envoyer le message
            success = await self._send_telegram_message(
                self.config.telegram_chat_id,
                formatted_message
            )
            
            if success:
                self.stats['messages_sent'] += 1
                self.stats['last_message_time'] = time.time()
                self.logger.info(f"Notification Telegram envoyée pour {message.token_data.symbol}")
            else:
                self.stats['messages_failed'] += 1
            
            return success
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi Telegram: {e}")
            self.stats['messages_failed'] += 1
            return False
    
    def _format_telegram_message(self, message: NotificationMessage) -> str:
        """Formater le message pour Telegram"""
        token = message.token_data
        
        # Utiliser le formatage Markdown de Telegram
        formatted_message = f"""🚨 *Nouveau Meme Coin Détecté sur Solana!* 🚀

*Nom:* {token.name}
*Symbole:* `{token.symbol}`
*Adresse:* `{token.mint_address}`

*Raisons de sélection:*
"""
        
        for reason in message.reasons:
            formatted_message += f"• {reason}\n"
        
        formatted_message += f"""
*Métriques actuelles:*
• Prix: ${token.current_price_usd:.8f}
• Market Cap: ${token.market_cap_usd:,.0f}
• Liquidité: ${token.liquidity_usd:,.0f}
• Volume 24h: ${token.volume_24h_usd:,.0f}
• Sentiment: {token.social_sentiment_score:.2f}/1.0

[Consulter sur Birdeye](https://birdeye.so/token/{token.mint_address})
[Consulter sur DexScreener](https://dexscreener.com/solana/{token.mint_address})

⚠️ *Attention: Investir dans les meme coins est très risqué. DYOR!*
"""
        
        return formatted_message
    
    async def _send_telegram_message(self, chat_id: str, message: str) -> bool:
        """Envoyer un message via l'API Telegram"""
        try:
            url = f"{self.base_url}/sendMessage"
            
            data = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }
            
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    return True
                else:
                    error_text = await response.text()
                    self.logger.error(f"Erreur API Telegram: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi du message Telegram: {e}")
            return False
    
    async def send_alert(self, title: str, message: str, urgency: str = 'medium') -> bool:
        """Envoyer une alerte simple"""
        try:
            emoji = "🔴" if urgency == 'high' else "🟡" if urgency == 'medium' else "🟢"
            formatted_message = f"{emoji} *{title}*\n\n{message}"
            
            return await self._send_telegram_message(
                self.config.telegram_chat_id,
                formatted_message
            )
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi d'alerte: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques"""
        return self.stats.copy()

class EmailNotifier:
    """Service de notification par email"""
    
    def __init__(self, config: NotificationConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Statistiques
        self.stats = {
            'emails_sent': 0,
            'emails_failed': 0,
            'last_email_time': 0
        }
    
    async def send_notification(self, message: NotificationMessage) -> bool:
        """Envoyer une notification par email"""
        try:
            if not self.config.email_enabled or not self.config.email_address:
                self.logger.warning("Email non configuré")
                return False
            
            # Formater le message
            subject, body = self._format_email_message(message)
            
            # Envoyer l'email
            success = await self._send_email(
                self.config.email_address,
                subject,
                body
            )
            
            if success:
                self.stats['emails_sent'] += 1
                self.stats['last_email_time'] = time.time()
                self.logger.info(f"Notification email envoyée pour {message.token_data.symbol}")
            else:
                self.stats['emails_failed'] += 1
            
            return success
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi email: {e}")
            self.stats['emails_failed'] += 1
            return False
    
    def _format_email_message(self, message: NotificationMessage) -> tuple[str, str]:
        """Formater le message pour email"""
        token = message.token_data
        
        subject = f"🚨 Nouveau Meme Coin Détecté: {token.symbol}"
        
        body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; }}
        .token-info {{ background-color: #f9f9f9; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .metrics {{ display: flex; flex-wrap: wrap; gap: 10px; }}
        .metric {{ background-color: #e7f3ff; padding: 10px; border-radius: 3px; flex: 1; min-width: 200px; }}
        .reasons {{ background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .warning {{ background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .links {{ text-align: center; margin: 20px 0; }}
        .links a {{ display: inline-block; margin: 0 10px; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚨 Nouveau Meme Coin Détecté sur Solana! 🚀</h1>
    </div>
    
    <div class="content">
        <div class="token-info">
            <h2>{token.name} ({token.symbol})</h2>
            <p><strong>Adresse du contrat:</strong> <code>{token.mint_address}</code></p>
        </div>
        
        <div class="reasons">
            <h3>Raisons de sélection:</h3>
            <ul>
"""
        
        for reason in message.reasons:
            body += f"                <li>{reason}</li>\n"
        
        body += f"""
            </ul>
        </div>
        
        <div class="metrics">
            <div class="metric">
                <strong>Prix actuel</strong><br>
                ${token.current_price_usd:.8f}
            </div>
            <div class="metric">
                <strong>Market Cap</strong><br>
                ${token.market_cap_usd:,.0f}
            </div>
            <div class="metric">
                <strong>Liquidité</strong><br>
                ${token.liquidity_usd:,.0f}
            </div>
            <div class="metric">
                <strong>Volume 24h</strong><br>
                ${token.volume_24h_usd:,.0f}
            </div>
            <div class="metric">
                <strong>Sentiment Social</strong><br>
                {token.social_sentiment_score:.2f}/1.0
            </div>
            <div class="metric">
                <strong>Mentions 24h</strong><br>
                {token.social_mentions_24h}
            </div>
        </div>
        
        <div class="links">
            <a href="https://birdeye.so/token/{token.mint_address}" target="_blank">Consulter sur Birdeye</a>
            <a href="https://dexscreener.com/solana/{token.mint_address}" target="_blank">Consulter sur DexScreener</a>
        </div>
        
        <div class="warning">
            <strong>⚠️ Avertissement:</strong> Investir dans les meme coins est extrêmement risqué. 
            Les prix peuvent être très volatils et vous pourriez perdre tout votre investissement. 
            Faites toujours vos propres recherches (DYOR) avant d'investir.
        </div>
    </div>
</body>
</html>
"""
        
        return subject, body
    
    async def _send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Envoyer un email"""
        try:
            # Créer le message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.config.email_username
            msg['To'] = to_email
            
            # Ajouter le contenu HTML
            html_part = MIMEText(body, 'html')
            msg.attach(html_part)
            
            # Envoyer via SMTP
            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.config.email_smtp_server, self.config.email_smtp_port) as server:
                server.starttls(context=context)
                server.login(self.config.email_username, self.config.email_password)
                server.send_message(msg)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi email: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques"""
        return self.stats.copy()

class NotificationQueue:
    """Gestionnaire de queue pour les notifications"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Queue interne pour les notifications
        self.notification_queue = Queue()
        
        # Kafka consumer pour les notifications
        self.kafka_consumer = None
        self.kafka_producer = None
        
        # Historique des notifications pour éviter les doublons
        self.notification_history = {}
        self.cooldown_period = 300  # 5 minutes
        
        # Statistiques
        self.stats = {
            'notifications_received': 0,
            'notifications_processed': 0,
            'notifications_skipped': 0,
            'queue_size': 0
        }
        
        self.running = False
    
    def start(self):
        """Démarrer le gestionnaire de queue"""
        self.running = True
        
        # Démarrer le consumer Kafka
        self._start_kafka_consumer()
        
        # Démarrer le processeur de queue
        self._start_queue_processor()
        
        self.logger.info("Gestionnaire de queue de notifications démarré")
    
    def stop(self):
        """Arrêter le gestionnaire de queue"""
        self.running = False
        
        if self.kafka_consumer:
            self.kafka_consumer.close()
        
        if self.kafka_producer:
            self.kafka_producer.close()
        
        self.logger.info("Gestionnaire de queue de notifications arrêté")
    
    def _start_kafka_consumer(self):
        """Démarrer le consumer Kafka"""
        try:
            self.kafka_consumer = KafkaConsumer(
                self.config.KAFKA_TOPICS['notifications'],
                bootstrap_servers=[self.config.KAFKA_BOOTSTRAP_SERVERS],
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                group_id='notification_service'
            )
            
            # Démarrer le thread de consommation
            consumer_thread = threading.Thread(target=self._kafka_consumer_loop)
            consumer_thread.daemon = True
            consumer_thread.start()
            
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage du consumer Kafka: {e}")
    
    def _kafka_consumer_loop(self):
        """Boucle de consommation Kafka"""
        while self.running:
            try:
                for message in self.kafka_consumer:
                    if not self.running:
                        break
                    
                    self.stats['notifications_received'] += 1
                    
                    # Ajouter à la queue interne
                    self.notification_queue.put(message.value)
                    self.stats['queue_size'] = self.notification_queue.qsize()
                    
            except Exception as e:
                self.logger.error(f"Erreur dans la boucle consumer Kafka: {e}")
                time.sleep(5)
    
    def _start_queue_processor(self):
        """Démarrer le processeur de queue"""
        processor_thread = threading.Thread(target=self._queue_processor_loop)
        processor_thread.daemon = True
        processor_thread.start()
    
    def _queue_processor_loop(self):
        """Boucle de traitement de la queue"""
        while self.running:
            try:
                if not self.notification_queue.empty():
                    notification_data = self.notification_queue.get(timeout=1)
                    self.stats['queue_size'] = self.notification_queue.qsize()
                    
                    # Traiter la notification
                    self._process_notification(notification_data)
                    self.stats['notifications_processed'] += 1
                else:
                    time.sleep(0.1)
                    
            except Exception as e:
                if self.running:  # Ignorer les erreurs lors de l'arrêt
                    self.logger.error(f"Erreur dans le processeur de queue: {e}")
                time.sleep(1)
    
    def _process_notification(self, notification_data: Dict[str, Any]):
        """Traiter une notification"""
        try:
            # Vérifier si c'est une notification de token
            if 'token_data' in notification_data:
                token_data = TokenData.from_dict(notification_data['token_data'])
                
                # Vérifier le cooldown
                if self._is_in_cooldown(token_data.mint_address):
                    self.stats['notifications_skipped'] += 1
                    return
                
                # Créer l'objet NotificationMessage
                notification = NotificationMessage(
                    token_data=token_data,
                    reasons=notification_data.get('reasons', []),
                    timestamp=notification_data.get('timestamp', int(time.time())),
                    channels=notification_data.get('channels', ['telegram'])
                )
                
                # Envoyer la notification
                asyncio.create_task(self._send_notification(notification))
                
                # Marquer comme envoyé
                self.notification_history[token_data.mint_address] = time.time()
            
            # Traiter d'autres types de notifications (alertes, etc.)
            elif notification_data.get('type') == 'price_alert':
                asyncio.create_task(self._send_price_alert(notification_data))
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement de la notification: {e}")
    
    def _is_in_cooldown(self, token_address: str) -> bool:
        """Vérifier si un token est en période de cooldown"""
        if token_address in self.notification_history:
            last_notification = self.notification_history[token_address]
            return time.time() - last_notification < self.cooldown_period
        return False
    
    async def _send_notification(self, notification: NotificationMessage):
        """Envoyer une notification (placeholder - sera implémenté par NotificationService)"""
        # Cette méthode sera appelée par NotificationService
        pass
    
    async def _send_price_alert(self, alert_data: Dict[str, Any]):
        """Envoyer une alerte de prix"""
        # Traiter les alertes de prix
        pass
    
    def add_notification(self, notification_data: Dict[str, Any]):
        """Ajouter une notification à la queue"""
        self.notification_queue.put(notification_data)
        self.stats['queue_size'] = self.notification_queue.qsize()
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques de la queue"""
        return {
            **self.stats,
            'queue_size': self.notification_queue.qsize()
        }

class NotificationService:
    """Service principal de notifications"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Configuration des notifications
        self.notification_config = NotificationConfig(
            telegram_enabled=config.NOTIFICATION_CHANNELS['telegram_enabled'],
            email_enabled=config.NOTIFICATION_CHANNELS['email_enabled'],
            telegram_chat_id=config.NOTIFICATION_CHANNELS['telegram_chat_id'],
            email_address=config.NOTIFICATION_CHANNELS['email_address']
        )
        
        # Services de notification
        self.telegram_notifier = TelegramNotifier(
            config.TELEGRAM_BOT_TOKEN,
            self.notification_config
        ) if config.TELEGRAM_BOT_TOKEN else None
        
        self.email_notifier = EmailNotifier(
            self.notification_config
        )
        
        # Gestionnaire de queue
        self.notification_queue = NotificationQueue(config)
        
        # Statistiques globales
        self.stats = {
            'total_notifications_sent': 0,
            'telegram_notifications': 0,
            'email_notifications': 0,
            'failed_notifications': 0
        }
        
        self.running = False
    
    async def start(self):
        """Démarrer le service de notifications"""
        self.running = True
        self.logger.info("Démarrage du service de notifications...")
        
        # Démarrer la queue
        self.notification_queue.start()
        
        # Remplacer la méthode de la queue pour envoyer les notifications
        self.notification_queue._send_notification = self._handle_notification
        self.notification_queue._send_price_alert = self._handle_price_alert
        
        # Démarrer les services de notification
        if self.telegram_notifier:
            await self.telegram_notifier.__aenter__()
        
        self.logger.info("Service de notifications démarré")
    
    async def stop(self):
        """Arrêter le service de notifications"""
        self.running = False
        self.logger.info("Arrêt du service de notifications...")
        
        # Arrêter la queue
        self.notification_queue.stop()
        
        # Arrêter les services de notification
        if self.telegram_notifier:
            await self.telegram_notifier.__aexit__(None, None, None)
        
        self.logger.info("Service de notifications arrêté")
    
    async def _handle_notification(self, notification: NotificationMessage):
        """Gérer l'envoi d'une notification"""
        try:
            success_count = 0
            
            # Envoyer via Telegram
            if 'telegram' in notification.channels and self.telegram_notifier:
                success = await self.telegram_notifier.send_notification(notification)
                if success:
                    success_count += 1
                    self.stats['telegram_notifications'] += 1
            
            # Envoyer via Email
            if 'email' in notification.channels and self.email_notifier:
                success = await self.email_notifier.send_notification(notification)
                if success:
                    success_count += 1
                    self.stats['email_notifications'] += 1
            
            if success_count > 0:
                self.stats['total_notifications_sent'] += 1
                self.logger.info(f"Notification envoyée avec succès pour {notification.token_data.symbol}")
            else:
                self.stats['failed_notifications'] += 1
                self.logger.error(f"Échec de l'envoi de notification pour {notification.token_data.symbol}")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi de notification: {e}")
            self.stats['failed_notifications'] += 1
    
    async def _handle_price_alert(self, alert_data: Dict[str, Any]):
        """Gérer l'envoi d'une alerte de prix"""
        try:
            mint_address = alert_data.get('mint_address', 'Unknown')
            price_change = alert_data.get('price_change_percent', 0)
            old_price = alert_data.get('old_price', 0)
            new_price = alert_data.get('new_price', 0)
            
            title = f"Alerte de Prix - {mint_address[:8]}..."
            message = f"""
Changement de prix significatif détecté!

Token: {mint_address}
Changement: {price_change:+.1f}%
Prix précédent: ${old_price:.8f}
Nouveau prix: ${new_price:.8f}

Consultez les graphiques pour plus de détails.
"""
            
            # Envoyer via Telegram
            if self.telegram_notifier:
                urgency = 'high' if abs(price_change) > 50 else 'medium'
                await self.telegram_notifier.send_alert(title, message, urgency)
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi d'alerte de prix: {e}")
    
    async def send_test_notification(self) -> Dict[str, bool]:
        """Envoyer une notification de test"""
        results = {}
        
        # Test Telegram
        if self.telegram_notifier:
            success = await self.telegram_notifier.send_alert(
                "Test de Notification",
                "Ceci est un test du système de notification Telegram.",
                "low"
            )
            results['telegram'] = success
        
        # Test Email
        if self.email_notifier and self.notification_config.email_enabled:
            # Créer une notification de test
            test_token = TokenData(
                mint_address="TEST123456789",
                symbol="TEST",
                name="Test Token",
                creation_timestamp=int(time.time()),
                supply=1000000,
                decimals=9,
                current_price_usd=0.001,
                market_cap_usd=1000,
                liquidity_usd=5000,
                volume_24h_usd=10000,
                price_change_1h_percent=5.0,
                price_change_24h_percent=10.0,
                social_sentiment_score=0.7,
                social_mentions_24h=25,
                community_engagement_score=0.8,
                last_updated_timestamp=int(time.time())
            )
            
            test_notification = NotificationMessage(
                token_data=test_token,
                reasons=["Test de notification"],
                timestamp=int(time.time()),
                channels=['email']
            )
            
            success = await self.email_notifier.send_notification(test_notification)
            results['email'] = success
        
        return results
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques complètes du service"""
        stats = {
            'service_stats': self.stats,
            'queue_stats': self.notification_queue.get_stats()
        }
        
        if self.telegram_notifier:
            stats['telegram_stats'] = self.telegram_notifier.get_stats()
        
        if self.email_notifier:
            stats['email_stats'] = self.email_notifier.get_stats()
        
        return stats
    
    def update_notification_config(self, new_config: Dict[str, Any]):
        """Mettre à jour la configuration des notifications"""
        for key, value in new_config.items():
            if hasattr(self.notification_config, key):
                setattr(self.notification_config, key, value)
        
        self.logger.info("Configuration des notifications mise à jour")
    
    async def send_system_status(self):
        """Envoyer un rapport de statut du système"""
        try:
            stats = self.get_comprehensive_stats()
            
            status_message = f"""📊 *Rapport de Statut du Bot*

*Service de Notifications:*
• Notifications envoyées: {stats['service_stats']['total_notifications_sent']}
• Notifications Telegram: {stats['service_stats']['telegram_notifications']}
• Notifications Email: {stats['service_stats']['email_notifications']}
• Échecs: {stats['service_stats']['failed_notifications']}

*Queue de Messages:*
• Messages reçus: {stats['queue_stats']['notifications_received']}
• Messages traités: {stats['queue_stats']['notifications_processed']}
• Messages ignorés: {stats['queue_stats']['notifications_skipped']}
• Taille actuelle: {stats['queue_stats']['queue_size']}

*Statut:* ✅ Opérationnel
*Dernière mise à jour:* {time.strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            if self.telegram_notifier:
                await self.telegram_notifier.send_alert(
                    "Rapport de Statut",
                    status_message,
                    "low"
                )
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi du statut: {e}")

