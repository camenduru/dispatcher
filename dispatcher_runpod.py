import http.server
import socketserver
import os
import json
import requests
import threading
from pymongo import MongoClient

mongodb_uri = os.getenv('com_camenduru_mongodb_uri')
worker_uri = os.getenv('com_camenduru_worker_uri')
runpod_token = os.getenv('com_camenduru_runpod_token')
job_type = os.getenv('com_camenduru_job_type')
job_source = os.getenv('com_camenduru_job_source')
server_port = os.getenv('com_camenduru_server_port')
web_uri = os.getenv('com_camenduru_web_uri')
web_token = os.getenv('com_camenduru_web_token')

def loop():
    client = MongoClient(mongodb_uri)
    db = client['web']
    collection_job = db['job']
    collection_detail = db['detail']

    def check_jobs():
        waiting_documents = collection_job.find({"$and":[ {"status":"WAITING"}, {"source":job_source}]})
        for waiting_document in waiting_documents:
            server = waiting_document['type']
            if(server==job_type):
                login = waiting_document['login']
                detail = collection_detail.find_one({"login": login})
                command = waiting_document['command']
                source_channel = waiting_document['source_channel']
                source_id = waiting_document['source_id']
                job_id = waiting_document['_id']
                if int(detail['total']) > 0:
                    collection_job.update_one({"_id": job_id}, {"$set": {"status": "WORKING"}})
                    command_data = json.loads(command)
                    command_data["source_id"] = source_id
                    command_data["source_channel"] = source_channel
                    command_data['job_id'] = str(job_id)
                    data = { "input": command_data }
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {runpod_token}"
                    }
                    try:
                        requests.post(worker_uri, headers=headers, json=data)
                    except Exception as e:
                        print(f"An unexpected error occurred: {e}")
                else:
                    try:
                        payload = {"jobId": str(job_id), "result": "Oops! Your balance is insufficient. Please redeem a Tost wallet code, or wait for the daily 100 free Tost wallet balance."}
                        requests.post(f"{web_uri}/api/notify", data=json.dumps(payload), headers={'Content-Type': 'application/json', "authorization": f"{web_token}"})
                    except Exception as e:
                        print(f"An unexpected error occurred: {e}")
        threading.Timer(1, check_jobs).start()
    check_jobs()

class MyHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = super().translate_path(path)
        if path.endswith('.py'):
            self.send_error(404, "File not found")
            return None
        return path
      
PORT = int(server_port)
Handler = MyHandler
Handler.extensions_map.update({
    '.html': 'text/html',
})

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    thread = threading.Thread(target=loop)
    thread.start()
    httpd.serve_forever()
