import http.server, socketserver, os, json
import requests, base64, threading
from pymongo import MongoClient

mongodb_uri = os.getenv('com_camenduru_mongodb_uri')
worker_uri = os.getenv('com_camenduru_worker_uri')
discord_token = os.getenv('com_camenduru_discord_token')
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
            try:
                from gradio_client import Client
                client = Client(worker_uri, verbose=False)
                result = client.predict(command, fn_index=0)
                file_extension = os.path.splitext(os.path.basename(result))[1]
                if(file_extension == ".png"):
                    files = {f"file.png": open(result, "rb").read()}
                elif(file_extension == ".mp4"):
                    files = {f"file.mp4": open(result, "rb").read()}
                payload = {"content": f"{command} <@{source_id}>"}
                try:
                    responseD = requests.post(f"https://discord.com/api/v9/channels/{source_channel}/messages", data=payload, headers={"authorization": f"Bot {discord_token}"}, files=files)
                    responseD.raise_for_status()
                    collection_job.update_one({"_id": waiting_document['_id']}, {"$set": {"status": "DONE"}})
                    collection_job.update_one({"_id": waiting_document['_id']}, {"$set": {"result": responseD.json()['attachments'][0]['url']}})
                    total = int(detail['total']) - int(amount)
                    collection_detail.update_one({"_id": detail['_id']}, {"$set": {"total": total}})
                    notify_response = requests.get(f"{notify_uri}/api/notify?login={login}")
                    notify_response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    print(f"D An error occurred: {e}")
                except Exception as e:
                    print(f"D An unexpected error occurred: {e}")
            except requests.exceptions.RequestException as e:
                print(f"F An error occurred: {e}")
            except Exception as e:
                print(f"F An unexpected error occurred: {e}")

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