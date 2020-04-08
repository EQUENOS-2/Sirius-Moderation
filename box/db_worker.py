import pymongo
from pymongo import MongoClient

app_string = f"{os.environ.get('cluster_app_string')}"
cluster = MongoClient(app_string)
