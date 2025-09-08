"""Kafka consumer для получения сообщений из топика step1 и создания комнат интервью."""

import json
import os
import time
import asyncio
from typing import Dict, Any, Optional, Callable
from kafka import KafkaConsumer
from kafka.errors import KafkaError, NoBrokersAvailable


class InterviewKafkaConsumer:
    """Kafka consumer для получения сообщений из топика step1."""
    
    def __init__(self, message_handler: Callable[[Dict[str, Any]], None]):
        self.kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
        self.kafka_topic_step1 = "step1"  # Топик для входящих сообщений
        self.kafka_connect_max_retries = int(os.getenv("KAFKA_CONNECT_MAX_RETRIES", "8") or 8)
        self.kafka_connect_backoff_seconds = float(os.getenv("KAFKA_CONNECT_BACKOFF_SECONDS", "2") or 2)
        self.kafka_consumer: Optional[KafkaConsumer] = None
        self.message_handler = message_handler
        self.is_running = False
        
        if self.kafka_bootstrap:
            print(f"🔍 Kafka Consumer инициализирован для топика: {self.kafka_topic_step1}")
        else:
            print("⚠️ KAFKA_BOOTSTRAP_SERVERS не установлена")

    def _build_kafka_config(self) -> Dict[str, Any]:
        """Создать конфигурацию для Kafka consumer."""
        servers = [s.strip() for s in self.kafka_bootstrap.split(",") if s.strip()]
        cfg = {
            "bootstrap_servers": servers,
            "value_deserializer": lambda m: json.loads(m.decode('utf-8')),
            "key_deserializer": lambda k: k.decode('utf-8') if k else None,
            "auto_offset_reset": "latest",
            "enable_auto_commit": True,
            "group_id": "interview_system_consumer",
            "session_timeout_ms": 30000,
            "heartbeat_interval_ms": 10000,
            "max_poll_records": 1,
            "consumer_timeout_ms": 1000,
        }
        
        # SSL конфигурация (если нужна)
        ssl_cafile = os.getenv("KAFKA_SSL_CAFILE")
        if ssl_cafile:
            cfg["security_protocol"] = "SSL"
            cfg["ssl_cafile"] = ssl_cafile
            
        return cfg

    def _create_kafka_consumer(self) -> KafkaConsumer:
        """Создать Kafka consumer."""
        cfg = self._build_kafka_config()
        consumer = KafkaConsumer(self.kafka_topic_step1, **cfg)
        return consumer

    def _ensure_kafka_connected_with_retries(self) -> bool:
        """Убедиться что Kafka подключена с повторными попытками."""
        if not self.kafka_bootstrap:
            print("❌ KAFKA_BOOTSTRAP_SERVERS не установлена")
            return False
            
        # Быстрый успешный путь
        if self.kafka_consumer is not None:
            try:
                # Проверяем что consumer активен
                _ = self.kafka_consumer.topics()
                return True
            except Exception:
                self.kafka_consumer = None

        attempts = 0
        backoff = max(self.kafka_connect_backoff_seconds, 0.5)
        last_error: Optional[Exception] = None
        
        while attempts < self.kafka_connect_max_retries:
            attempts += 1
            try:
                self.kafka_consumer = self._create_kafka_consumer()
                # Проверяем доступность топика
                try:
                    topics = self.kafka_consumer.topics()
                    if self.kafka_topic_step1 in topics:
                        print(f"✅ Kafka Consumer подключен после {attempts} попыток")
                        return True
                    else:
                        print(f"⚠️ Топик {self.kafka_topic_step1} не найден")
                        return False
                except Exception:
                    pass
                return True
            except (NoBrokersAvailable, KafkaError, Exception) as e:
                last_error = e
                if attempts < self.kafka_connect_max_retries:
                    print(f"⚠️ Попытка {attempts}/{self.kafka_connect_max_retries} подключения к Kafka неудачна: {e}")
                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, 30.0)  # Экспоненциальная задержка, макс 30 сек
                else:
                    print(f"❌ Не удалось подключиться к Kafka после {attempts} попыток: {last_error}")
                    return False

        return False

    async def start_consuming(self):
        """Начать потребление сообщений из Kafka."""
        if not self._ensure_kafka_connected_with_retries():
            print("❌ Не удалось подключиться к Kafka для потребления сообщений")
            return
            
        self.is_running = True
        print(f"🚀 Начинаем потребление сообщений из топика {self.kafka_topic_step1}")
        print(f"🔧 Consumer настройки: bootstrap_servers={self.kafka_bootstrap}")
        
        try:
            while self.is_running:
                try:
                    # Получаем сообщения с таймаутом
                    message_batch = self.kafka_consumer.poll(timeout_ms=1000)
                    
                    if message_batch:
                        for topic_partition, messages in message_batch.items():
                            for message in messages:
                                try:
                                    print(f"📨 Получено сообщение из {topic_partition.topic}")
                                    print(f"📋 Ключ: {message.key}")
                                    
                                    # Обрабатываем сообщение
                                    await self._process_message(message.value)
                                    
                                except Exception as e:
                                    print(f"❌ Ошибка обработки сообщения: {e}")
                                    continue
                    
                except Exception as e:
                    print(f"❌ Ошибка при получении сообщений: {e}")
                    # Пытаемся переподключиться
                    self.kafka_consumer = None
                    if not self._ensure_kafka_connected_with_retries():
                        print("❌ Не удалось переподключиться к Kafka")
                        break
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            print("🛑 Получен сигнал остановки")
        finally:
            self.stop_consuming()

    async def _process_message(self, message_data: Dict[str, Any]):
        """Обработать полученное сообщение."""
        try:
            print(f"📊 Обработка сообщения для кандидата: {message_data.get('candidateName', 'Неизвестно')}")
            print(f"🆔 Candidate ID: {message_data.get('candidateId', 'Неизвестно')}")
            
            # Вызываем обработчик сообщения
            if self.message_handler:
                await self.message_handler(message_data)
            else:
                print("⚠️ Обработчик сообщений не установлен")
                
        except Exception as e:
            print(f"❌ Ошибка обработки сообщения: {e}")

    def stop_consuming(self):
        """Остановить потребление сообщений."""
        self.is_running = False
        if self.kafka_consumer:
            try:
                self.kafka_consumer.close()
                print("✅ Kafka Consumer закрыт")
            except Exception as e:
                print(f"⚠️ Ошибка закрытия Kafka Consumer: {e}")


# Глобальный экземпляр consumer
_kafka_consumer: Optional[InterviewKafkaConsumer] = None


def get_kafka_consumer(message_handler: Callable[[Dict[str, Any]], None]) -> InterviewKafkaConsumer:
    """Получить глобальный экземпляр Kafka consumer."""
    global _kafka_consumer
    if _kafka_consumer is None:
        _kafka_consumer = InterviewKafkaConsumer(message_handler)
    return _kafka_consumer


def start_kafka_consumer(message_handler: Callable[[Dict[str, Any]], None]):
    """Удобная функция для запуска Kafka consumer."""
    print("🔧 Инициализация Kafka consumer...")
    consumer = get_kafka_consumer(message_handler)
    print("🔧 Consumer получен, запускаем в отдельном потоке...")
    # Запускаем в отдельном потоке, чтобы не блокировать startup
    import threading
    
    def run_consumer():
        print("🔧 Запуск consumer в отдельном потоке...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            print("🔧 Запуск start_consuming...")
            loop.run_until_complete(consumer.start_consuming())
        except Exception as e:
            print(f"❌ Ошибка в consumer: {e}")
            import traceback
            traceback.print_exc()
        finally:
            loop.close()
    
    thread = threading.Thread(target=run_consumer, daemon=True)
    thread.start()
    print("✅ Kafka consumer запущен в отдельном потоке")
    
    # Возвращаем consumer для дальнейшего использования
    return consumer
