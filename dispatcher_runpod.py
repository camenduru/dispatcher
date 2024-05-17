import http.server, socketserver, os, json
import requests, base64, threading
from pymongo import MongoClient

mongodb_uri = os.getenv('com_camenduru_mongodb_uri')
worker_uri = os.getenv('com_camenduru_worker_uri')
runpod_token = os.getenv('com_camenduru_runpod_token')
job_type = os.getenv('com_camenduru_job_type')
job_source = os.getenv('com_camenduru_job_source')
server_port = os.getenv('com_camenduru_server_port')
notify_uri = os.getenv('com_camenduru_notify_uri')

def loop():
  client = MongoClient(mongodb_uri)
  db = client['web']
  collection_job = db['job']
  collection_detail = db['detail']

  while True:
    waiting_documents = collection_job.find({"$and":[ {"status":"WAITING"}, {"source":job_source}]})
    for waiting_document in waiting_documents:
        server = waiting_document['type']
        if(server==job_type):
            login = waiting_document['login']
            detail = collection_detail.find_one({"login": login})
            amount = waiting_document['amount']
            command = waiting_document['command']
            source_channel = waiting_document['source_channel']
            source_id = waiting_document['source_id']
            collection_job.update_one({"_id": waiting_document['_id']}, {"$set": {"status": "WORKING"}})
            command_data = json.loads(command)
            command_data["source_id"] = source_id
            command_data["source_channel"] = source_channel
            data = { "input": command_data }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {runpod_token}"
            }
            try:
                response = requests.post(worker_uri, headers=headers, json=data)
                print(response.json()['status'])
                print(response.json()['output']['result'])
                if(response.json()['status'] == "COMPLETED" and response.json()['output']['result'] != "ERROR"):
                    collection_job.update_one({"_id": waiting_document['_id']}, {"$set": {"status": "DONE"}})
                    collection_job.update_one({"_id": waiting_document['_id']}, {"$set": {"result": response.json()['output']['result']}})
                    total = int(detail['total']) - int(amount)
                    collection_detail.update_one({"_id": detail['_id']}, {"$set": {"total": total}})
                    notify_response = requests.get(f"{notify_uri}/api/notify?login={login}")
                    notify_response.raise_for_status()
            except Exception as e:
                print(f"An unexpected error occurred: {e}")

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
    print(f"Server running on port {PORT}")
    httpd.serve_forever()