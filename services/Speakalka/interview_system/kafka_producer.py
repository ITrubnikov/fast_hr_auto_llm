"""Kafka producer для отправки отчетов интервью."""

import json
import os
import time
from typing import Dict, Any, Optional
from kafka import KafkaProducer
from kafka.errors import KafkaError, NoBrokersAvailable


class InterviewKafkaProducer:
    """Kafka producer для отправки отчетов интервью в топик step3."""
    
    def __init__(self):
        self.kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
        self.kafka_topic = os.getenv("KAFKA_TOPIC", "step3").strip()
        self.kafka_connect_max_retries = int(os.getenv("KAFKA_CONNECT_MAX_RETRIES", "8") or 8)
        self.kafka_connect_backoff_seconds = float(os.getenv("KAFKA_CONNECT_BACKOFF_SECONDS", "2") or 2)
        self.kafka_producer: Optional[KafkaProducer] = None
        
        if self.kafka_bootstrap and self.kafka_topic:
            # Первая попытка создать продьюсер (без долгой блокировки)
            try:
                self.kafka_producer = self._create_kafka_producer()
                print(f"✅ Kafka producer инициализирован для топика: {self.kafka_topic}")
            except Exception as e:
                print(f"⚠️ Kafka недоступна при старте: {e}")

    def _build_kafka_config(self) -> Dict[str, Any]:
        """Создать конфигурацию для Kafka producer."""
        servers = [s.strip() for s in self.kafka_bootstrap.split(",") if s.strip()]
        cfg = {
            "bootstrap_servers": servers,
            "value_serializer": lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            "key_serializer": lambda k: k.encode("utf-8") if k else None,
            "acks": "all",
            "retries": 3,
            "batch_size": 16384,
            "linger_ms": 5,
            "buffer_memory": 33554432,
            "max_block_ms": 10000,
            "request_timeout_ms": 30000,
        }
        
        # SSL конфигурация (если нужна)
        ssl_cafile = os.getenv("KAFKA_SSL_CAFILE")
        if ssl_cafile:
            cfg["security_protocol"] = "SSL"
            cfg["ssl_cafile"] = ssl_cafile
            
        return cfg

    def _create_kafka_producer(self) -> KafkaProducer:
        """Создать Kafka producer."""
        cfg = self._build_kafka_config()
        producer = KafkaProducer(**cfg)
        return producer

    def _ensure_kafka_connected_with_retries(self) -> bool:
        """Убедиться что Kafka подключена с повторными попытками."""
        if not (self.kafka_bootstrap and self.kafka_topic):
            return False
            
        # Быстрый успешный путь
        if self.kafka_producer is not None:
            try:
                if self.kafka_producer.bootstrap_connected():
                    return True
            except Exception:
                self.kafka_producer = None

        attempts = 0
        backoff = max(self.kafka_connect_backoff_seconds, 0.5)
        last_error: Optional[Exception] = None
        
        while attempts < self.kafka_connect_max_retries:
            attempts += 1
            try:
                self.kafka_producer = self._create_kafka_producer()
                # Проверяем доступность метаданных/брокера
                try:
                    _ = self.kafka_producer.partitions_for(self.kafka_topic)
                except Exception:
                    pass
                if self.kafka_producer.bootstrap_connected():
                    print(f"✅ Kafka подключена после {attempts} попыток")
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

    def publish_interview_report(self, report: Dict[str, Any]) -> bool:
        """Отправить отчет интервью в Kafka."""
        if not self.kafka_producer or not self.kafka_topic:
            # Пытаемся подключиться лениво при первой отправке
            if not self._ensure_kafka_connected_with_retries():
                print("❌ Не удалось подключиться к Kafka для отправки отчета")
                return False
                
        try:
            # Добавляем метаданные к отчету
            report_with_metadata = {
                "timestamp": time.time(),
                "source": "interview_system",
                "topic": self.kafka_topic,
                "report": report
            }
            
            # Отправляем в Kafka
            future = self.kafka_producer.send(
                self.kafka_topic, 
                value=report_with_metadata,
                key=f"interview_{report.get('candidate_name', 'unknown')}_{int(time.time())}"
            )
            
            # Ждем подтверждения
            record_metadata = future.get(timeout=10)
            print(f"✅ Отчет отправлен в Kafka топик {self.kafka_topic}, partition: {record_metadata.partition}, offset: {record_metadata.offset}")
            return True
            
        except (KafkaError, Exception) as e:
            print(f"❌ Ошибка отправки отчета в Kafka: {e}")
            # Пытаемся разово пересоздать продьюсер и повторить
            self.kafka_producer = None
            if self._ensure_kafka_connected_with_retries():
                try:
                    future = self.kafka_producer.send(
                        self.kafka_topic, 
                        value=report_with_metadata,
                        key=f"interview_{report.get('candidate_name', 'unknown')}_{int(time.time())}"
                    )
                    record_metadata = future.get(timeout=10)
                    print(f"✅ Отчет отправлен в Kafka после переподключения, partition: {record_metadata.partition}, offset: {record_metadata.offset}")
                    return True
                except Exception as retry_error:
                    print(f"❌ Ошибка повторной отправки в Kafka: {retry_error}")
                    return False
            return False

    def close(self):
        """Закрыть Kafka producer."""
        if self.kafka_producer:
            try:
                self.kafka_producer.flush(timeout=5)
                self.kafka_producer.close()
                print("✅ Kafka producer закрыт")
            except Exception as e:
                print(f"⚠️ Ошибка закрытия Kafka producer: {e}")


# Глобальный экземпляр producer
_kafka_producer: Optional[InterviewKafkaProducer] = None


def get_kafka_producer() -> InterviewKafkaProducer:
    """Получить глобальный экземпляр Kafka producer."""
    global _kafka_producer
    if _kafka_producer is None:
        _kafka_producer = InterviewKafkaProducer()
    return _kafka_producer


def publish_report_to_kafka(report: Dict[str, Any]) -> bool:
    """Удобная функция для отправки отчета в Kafka."""
    producer = get_kafka_producer()
    return producer.publish_interview_report(report)
