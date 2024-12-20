import json
import logging
import os

import requests
from paho.mqtt import client as mqtt


class Enrichment:
    """
    Represents the enrcihment service

    ## Attributes

    logger (logging.Logger): module level logger object

    producer (mqtt.Client): mosquitto producer object to publish data

    subscriber (mqtt.Client): mosquitto subscriber object to consume data

    """

    def __init__(self) -> None:
        self.logger: logging.Logger = self.create_logger()
        self.producer: mqtt.Client = self.create_mqtt_producer()
        self.subscriber: mqtt.Client = None

    def start(self) -> None:
        """
        start the enrichment service.

        initializes the mosquitto subscriber to start consuming messages
        """

        broker_host = os.getenv("MQTT_HOST")
        broker_port = os.getenv("MQTT_PORT")

        self.subscriber = self.create_mqtt_subscriber()
        self.subscriber.connect(broker_host, int(broker_port))
        self.subscriber.loop_forever()

    def create_logger(self) -> logging.Logger:
        """
        Setup and configure the logger for this module

        ## Returns

        configured logger object for this module
        """

        logger = logging.Logger(__name__)
        console_handler = logging.StreamHandler()
        logger.addHandler(console_handler)
        formatter = logging.Formatter(
            fmt="{asctime} - {name} - {levelname} - {message}",
            style="{",
            datefmt="%Y-%m-%d %H:%M",
        )
        console_handler.setFormatter(formatter)
        logger.setLevel(os.environ.get("LOGGING_LEVEL"))
        logger.info("Starting Enrichment service...")
        return logger

    def create_mqtt_producer(self) -> mqtt.Client:
        """
        Configure the mqtt producer

        ## Returns

        A `mqtt.Client` object
        """

        broker_host = os.getenv("MQTT_HOST")
        broker_port = os.getenv("MQTT_PORT")
        client = mqtt.Client()
        client.tls_set("ca.crt")
        client.tls_insecure_set(True)
        client.on_connect = self.__producer_on_connect
        client.on_publish = self.__producer_on_publish
        client.connect(broker_host, int(broker_port))
        client.loop_start()
        return client

    def create_mqtt_subscriber(self) -> mqtt.Client:
        """
        Configure the mqtt subscriber

        ## Returns

        A `mqtt.Client` object
        """

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.tls_set("ca.crt")
        client.tls_insecure_set(True)
        client.on_connect = self.__subscriber_on_connect
        client.on_message = self.__subscrber_on_message

        return client

    def __producer_on_connect(self, client, userdata, flags, reason_code):
        """
        When connected with mqtt broker
        """

        if reason_code == 0:
            self.logger.info(f"Publisher connected with mqtt broker {reason_code}")
        else:
            self.logger.error(
                f"Failed to connect with broker with result: {reason_code}")

    def __producer_on_publish(self, client, userdata, mid):
        """
        when messge is published to broker
        """

        self.logger.debug(f"Msg published {mid}")

    def __subscriber_on_connect(self, client, userdata, flags, reason_code, properties):
        """
        When connected with the broker then subscribe to the topic
        """

        if reason_code.is_failure:
            self.logger.error(f"Failed to connect: {reason_code}. loop_forever() will retry connection")
        else:
            self.logger.info(f"Subscriber connected with broker")
            self.subscriber.subscribe(f"{os.environ.get("MQTT_TOPIC_RAW")}/#")

    def __subscrber_on_message(self, client, userdata, message):
        """
        When message is recieved, perform enrichemnt
        """

        decoded_data = json.loads(message.payload.decode("utf-8"))
        self.check_ip(decoded_data)

    def check_ip(self, data):
        """
        Enrich ip data using abuseipdb api
        """

        src_ip = data.get("data").get("src_ip")
        if src_ip:
            response = requests.get(
                url="https://api.abuseipdb.com/api/v2/check",
                params={"maxAgeInDays": 90, "ipAddress": src_ip},
                headers={"Key": os.environ.get(
                    "ABUSEIPDB_API_KEY"), "accept": "application/json"}
            )

            data["data"].update({"abuse_ipdb": response.json().get("data")})
            self.producer.publish(
                topic=os.environ.get("MQTT_TOPIC_ENRICHED"),
                payload=json.dumps(data).encode('utf-8'),
                qos=0,
                retain=False
            )
