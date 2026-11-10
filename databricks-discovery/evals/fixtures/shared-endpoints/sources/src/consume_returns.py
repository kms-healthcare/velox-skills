import sys

from confluent_kafka import Consumer
from pyspark.sql import SparkSession

bootstrap, topic = sys.argv[1:3]

spark = SparkSession.builder.getOrCreate()
consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": "returns-loader", "enable.auto.commit": False})
consumer.subscribe([topic])
while (msg := consumer.poll(5.0)) is not None:
    spark.createDataFrame([(msg.value().decode(),)], ["payload"]).write.mode("append").saveAsTable("bronze.returns")
    consumer.commit(msg)
consumer.close()
