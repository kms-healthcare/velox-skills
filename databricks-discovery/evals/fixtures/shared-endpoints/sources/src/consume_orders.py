import sys

from confluent_kafka import Consumer
from pyspark.sql import SparkSession

bootstrap, topic, group, enabled = sys.argv[1:5]

if enabled.lower() != "true":
    print("orders consumer disabled for this target")
    sys.exit(0)

spark = SparkSession.builder.getOrCreate()
consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": group, "enable.auto.commit": False})
consumer.subscribe([topic])
while (msg := consumer.poll(5.0)) is not None:
    spark.createDataFrame([(msg.value().decode(),)], ["payload"]).write.mode("append").saveAsTable("bronze.orders")
    consumer.commit(msg)
consumer.close()
