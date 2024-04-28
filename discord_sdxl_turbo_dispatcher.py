import http.server, socketserver, os, json
import requests, base64, threading
from pymongo import MongoClient

mongodb = os.getenv('com_camenduru_web_data_mongodb_uri')
api = os.getenv('com_camenduru_discord_api_url')
token = os.getenv('com_camenduru_discord_token')
job = os.getenv('com_camenduru_discord_job_type')

def loop():
  client = MongoClient(mongodb)
  db = client['web']
  collection_job = db['job']
  collection_detail = db['detail']

  while True:
    waiting_documents = collection_job.find({"status": "WAITING"})
    for waiting_document in waiting_documents:
        detail = waiting_document['discord']
        discord = collection_detail.find_one({"_id": detail.id})['discord']
        total = collection_detail.find_one({"_id": detail.id})['total']
        server = waiting_document['type']
        if(server==job):
            amount = waiting_document['amount']
            command = waiting_document['command']
            source_channel = waiting_document['source_channel']
            source_id = waiting_document['source_id']
            collection_job.update_one({"_id": waiting_document['_id']}, {"$set": {"status": "WORKING"}})
            try:
                from gradio_client import Client
                client = Client(api, verbose=False)
                result = client.predict(command, fn_index=0)
                files = {f"image.png": open(result, "rb").read()}
                payload = {"content": f"{command} <@{source_id}>"}
                try:
                    responseD = requests.post(f"https://discord.com/api/v9/channels/{source_channel}/messages", data=payload, headers={"authorization": f"Bot {token}"}, files=files)
                    responseD.raise_for_status()
                    collection_job.update_one({"_id": waiting_document['_id']}, {"$set": {"status": "DONE"}})
                    collection_job.update_one({"_id": waiting_document['_id']}, {"$set": {"result": responseD.json()['attachments'][0]['url']}})
                    total = int(total) - int(amount)
                    collection_detail.update_one({"_id": detail.id}, {"$set": {"total": total}})
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
      
PORT = os.getenv('server_port')
Handler = MyHandler
Handler.extensions_map.update({
    '.html': 'text/html',
})

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    thread = threading.Thread(target=loop)
    thread.start()
    print(f"Server running on port {PORT}")
    httpd.serve_forever()