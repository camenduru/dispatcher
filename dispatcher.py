import http.server
import socketserver
import os
import json
import requests
import threading
from pymongo import MongoClient

mongodb_uri = os.getenv('com_camenduru_mongodb_uri')
worker_uri = os.getenv('com_camenduru_worker_uri')
discord_token = os.getenv('com_camenduru_discord_token')
job_type = os.getenv('com_camenduru_job_type')
job_source = os.getenv('com_camenduru_job_source')
server_port = os.getenv('com_camenduru_server_port')
web_uri = os.getenv('com_camenduru_web_uri')
web_token = os.getenv('com_camenduru_web_token')

def loop():
    client = MongoClient(mongodb_uri)
    db = client['web']
    collection_job = db['job']

    def check_jobs():
        waiting_documents = collection_job.find({"$and":[ {"status":"WAITING"}, {"source":job_source}]})
        for waiting_document in waiting_documents:
            server = waiting_document['type']
            if(server==job_type):
                command = waiting_document['command']
                source_channel = waiting_document['source_channel']
                source_id = waiting_document['source_id']
                job_id = waiting_document['_id']
                collection_job.update_one({"_id": job_id}, {"$set": {"status": "WORKING"}})
                try:
                    from gradio_client import Client
                    client = Client(worker_uri, verbose=False)
                    result = client.predict(command, fn_index=0)
                    if isinstance(result, str):
                        file_path = result
                        default_filename = os.path.basename(file_path)
                        files = {default_filename: open(file_path, "rb").read()}
                    elif isinstance(result, dict):
                        file_path = result.get('video')
                        default_filename = os.path.basename(file_path)
                        files = {default_filename: open(file_path, "rb").read()}
                    elif isinstance(result, tuple):
                        first_key = next(iter(result[0]))
                        file_path = result[0][first_key]
                        file_paths = result[1]
                        default_filename = os.path.basename(file_path)
                        files = { default_filename: open(file_path, "rb").read() }
                        for path in file_paths:
                            filename = os.path.basename(path)
                            with open(path, "rb") as file:
                                files[filename] = file.read()
                    payload = {"content": f"{command} <@{source_id}>"}
                    response = None
                    try:
                        response = requests.post(f"https://discord.com/api/v9/channels/{source_channel}/messages", data=payload, headers={"authorization": f"Bot {discord_token}"}, files=files)
                        response.raise_for_status()
                    except Exception as e:
                        print(f"Discord an unexpected error occurred: {e}")
                    if response and response.status_code == 200:
                        try:
                            if isinstance(result, str):
                                payload = {"jobId": str(job_id), "result": response.json()['attachments'][0]['url']}
                            elif isinstance(result, dict):
                                payload = {"jobId": str(job_id), "result": response.json()['attachments'][0]['url']}
                            elif isinstance(result, tuple):
                                urls = [attachment['url'] for attachment in response.json()['attachments']]
                                payload = {"jobId": str(job_id), "result": str(urls)}
                            requests.post(f"{web_uri}/api/notify", data=json.dumps(payload), headers={'Content-Type': 'application/json', "authorization": f"{web_token}"})
                        except Exception as e:
                            print(f"An unexpected error occurred: {e}")
                except Exception as e:
                    print(f"Client an unexpected error occurred: {e}")

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
