import pymongo
from pymongo import MongoClient
import os

app_string = f"{os.environ.get('cluster_app_string')}"
cluster = MongoClient(app_string)
