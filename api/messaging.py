import json
import os
import time
import uuid

import pika

import metrics

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "")
ENABLED = bool(RABBITMQ_URL)


def _connect(retries=30, delay=2):
    for attempt in range(1, retries + 1):
        try:
            return pika.BlockingConnection(
                pika.URLParameters(RABBITMQ_URL)
            )
        except pika.exceptions.AMQPConnectionError:
            print(
                f"RabbitMQ not ready (attempt {attempt}/{retries})",
                flush=True
            )
            time.sleep(delay)

    raise RuntimeError("Could not connect to RabbitMQ")


def envelope(event_type, correlation_id, payload):
    return {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "correlation_id": correlation_id,
        "event_type": event_type,
        "payload": payload
    }


def publish(queue, message):

    if not ENABLED:
        return False

    connection = _connect(retries=5)

    try:
        channel = connection.channel()
        channel.queue_declare(queue=queue, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=queue,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json"
            )
        )
    finally:
        connection.close()

    return True


def consume(queue, handler):
    
    if not ENABLED:
        return

    while True:
        try:
            connection = _connect()
            channel = connection.channel()
            channel.queue_declare(queue=queue, durable=True)
            channel.basic_qos(prefetch_count=1)

            def on_message(ch, method, properties, body):
                try:
                    handler(json.loads(body))
                    ch.basic_ack(method.delivery_tag)
                    metrics.queue_messages.labels(
                        queue=queue, outcome="ok"
                    ).inc()
                except Exception as error:
                    print(
                        f"Failed to handle message on {queue}: {error}",
                        flush=True
                    )
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    metrics.queue_messages.labels(
                        queue=queue, outcome="error"
                    ).inc()

            channel.basic_consume(
                queue=queue,
                on_message_callback=on_message
            )

            print(f"Consuming {queue}", flush=True)
            channel.start_consuming()
        except Exception as error:
            print(f"Consumer for {queue} stopped: {error}", flush=True)
            time.sleep(3)