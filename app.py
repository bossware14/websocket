from flask import Flask, render_template
from flask_socketio import SocketIO, emit, send
from flask_cors import CORS, cross_origin
import requests
import time
import gpiod
import subprocess
import os
import signal
import json
from datetime import datetime, timezone, timedelta
import socket
import RPi.GPIO as GPIO


GP1 = 17
GP2 = 22
GP3 = 23
GP4 = 27

app = Flask(__name__,template_folder="")
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)
CORS(app)

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

#GPIO.setup(GP1,GPIO.IN)
#GPIO.setup(GP2,GPIO.IN)
#GPIO.setup(GP3,GPIO.IN)
#GPIO.setup(GP4,GPIO.IN)

if os.path.isfile('data.json'):
    with open('data.json', 'r') as f:
      json_data = json.load(f)
else:
    json_data = {}
    with open('data.json', 'w') as f:
      json.dump(json_data, f) 

@app.route('/')
def index():
    return render_template('index.html')

@socketio.event()
def my_event(message):
    emit('response', {'data': 'got it!'})

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(('10.254.254.254', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

print(os.uname())

def update_data(json_data):
    tz = timezone(timedelta(hours = 7))
    json_data['time'] = datetime.now(tz=tz).strftime('%Y-%m-%d %H:%M:%S')
    with open('data.json', 'w') as f:
        json.dump(json_data, f) 
    return json_data

@app.route('/api')
def get_api():
    tz = timezone(timedelta(hours = 7))
    json_data['time'] = datetime.now(tz=tz).strftime('%Y-%m-%d %H:%M:%S')
    return update_data(json_data),200

@socketio.on('message')
def handleMessage(msg):
    if msg == 'connect':
        return send(update_data(json_data), broadcast=True)
    else:
       res = json.loads(msg)
       print(res)
       if res["status"] == 'message':
          return send(update_data(json_data), broadcast=True)
       if res["status"] == 'start':
          if res['data'] == True :
             GPIO.setup(int(res['value']),GPIO.OUT)
          if res['data'] == False :
             GPIO.setup(int(res['value']),GPIO.IN)

          return send(update_data(json_data), broadcast=True)

       if res["status"] == 'update':
          json_data[res["key"]] = res["value"]
          return send(update_data(json_data), broadcast=True)
       return send(json_data, broadcast=True)


@socketio.on_error()
def error_handler(e):
    print(f'An error occurred: {e}')

if __name__ == '__main__':
    socketio.run(app,host="0.0.0.0",port="5000", debug=True)
    #socketio.run(app,host="0.0.0.0",port="5000", debug=True,ssl_context=('cert.pem', 'key.pem'))
