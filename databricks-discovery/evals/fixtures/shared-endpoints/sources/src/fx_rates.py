import sys

import requests
from pyspark.sql import SparkSession

url = sys.argv[1]

rates = requests.get(f"{url}/rates", params={"base": "EUR"}, timeout=30).json()["rates"]
spark = SparkSession.builder.getOrCreate()
spark.createDataFrame(list(rates.items()), ["currency", "rate"]).write.mode("overwrite").saveAsTable("silver.fx_rates")
