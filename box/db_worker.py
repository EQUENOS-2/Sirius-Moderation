import pymongo
from pymongo import MongoClient

app_string = open("box/cluster_app_string.txt", "r").read() #f"{os.environ.get('cluster_app_string')}"
cluster = MongoClient(app_string)