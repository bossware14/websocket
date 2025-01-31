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


HexDigits = [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 
            0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71, 0x3D, 0x76, 
            0x06, 0x1E, 0x76, 0x38, 0x55, 0x54, 0x3F, 0x73, 0x67, 
            0x50, 0x6D, 0x78, 0x3E, 0x1C, 0x2A, 0x76, 0x6E, 0x5B,
            0x00, 0x40, 0x63, 0xFF]

ADDR_AUTO = 0x40
ADDR_FIXED = 0x44
STARTADDR = 0xC0
# DEBUG = False

class TM1637:
    __doublePoint = False
    __Clkpin = 0
    __Datapin = 0
    __brightness = 1.0  # default to max brightness
    __currentData = [0, 0, 0, 0]

    def __init__(self, CLK, DIO, brightness):
        self.__Clkpin = CLK
        self.__Datapin = DIO
        self.__brightness = brightness
        GPIO.setup(self.__Clkpin, GPIO.OUT)
        GPIO.setup(self.__Datapin, GPIO.OUT)

    def cleanup(self):
        """Stop updating clock, turn off display, and cleanup GPIO"""
        self.StopClock()
        self.Clear()
        GPIO.cleanup()

    def Clear(self):
        b = self.__brightness
        point = self.__doublePoint
        self.__brightness = 0
        self.__doublePoint = False
        data = [0x7F, 0x7F, 0x7F, 0x7F]
        self.Show(data)
        # Restore previous settings:
        self.__brightness = b
        self.__doublePoint = point

    def ShowInt(self, i):
        s = str(i)
        self.Clear()
        for i in range(0, len(s)):
            self.Show1(i, int(s[i]))

    def Show(self, data):
        for i in range(0, 4):
            self.__currentData[i] = data[i]

        self.start()
        self.writeByte(ADDR_AUTO)
        self.br()
        self.writeByte(STARTADDR)
        for i in range(0, 4):
            self.writeByte(self.coding(data[i]))
        self.br()
        self.writeByte(0x88 + int(self.__brightness))
        self.stop()

    def Show1(self, DigitNumber, data):
        """show one Digit (number 0...3)"""
        if(DigitNumber < 0 or DigitNumber > 3):
            return  # error

        self.__currentData[DigitNumber] = data

        self.start()
        self.writeByte(ADDR_FIXED)
        self.br()
        self.writeByte(STARTADDR | DigitNumber)
        self.writeByte(self.coding(data))
        self.br()
        self.writeByte(0x88 + int(self.__brightness))
        self.stop()
    # Scrolls any integer n (can be more than 4 digits) from right to left display.
    def ShowScroll(self, n):
        n_str = str(n)
        k = len(n_str)

        for i in range(0, k + 4):
            if (i < k):
                self.Show([int(n_str[i-3]) if i-3 >= 0 else None, int(n_str[i-2]) if i-2 >= 0 else None, int(n_str[i-1]) if i-1 >= 0 else None, int(n_str[i]) if i >= 0 else None])
            elif (i >= k):
                self.Show([int(n_str[i-3]) if (i-3 < k and i-3 >= 0) else None, int(n_str[i-2]) if (i-2 < k and i-2 >= 0) else None, int(n_str[i-1]) if (i-1 < k and i-1 >= 0) else None, None])
            time.sleep(1)

    def SetBrightness(self, percent):
        """Accepts percent brightness from 0 - 1"""
        max_brightness = 7.0
        brightness = math.ceil(max_brightness * percent)
        if (brightness < 0):
            brightness = 0
        if(self.__brightness != brightness):
            self.__brightness = brightness
            self.Show(self.__currentData)

    def ShowDoublepoint(self, on):
        """Show or hide double point divider"""
        if(self.__doublePoint != on):
            self.__doublePoint = on
            self.Show(self.__currentData)

    def writeByte(self, data):
        for i in range(0, 8):
            GPIO.output(self.__Clkpin, GPIO.LOW)
            if(data & 0x01):
                GPIO.output(self.__Datapin, GPIO.HIGH)
            else:
                GPIO.output(self.__Datapin, GPIO.LOW)
            data = data >> 1
            GPIO.output(self.__Clkpin, GPIO.HIGH)
 
        # wait for ACK
        GPIO.output(self.__Clkpin, GPIO.LOW)
        GPIO.output(self.__Datapin, GPIO.HIGH)
        GPIO.output(self.__Clkpin, GPIO.HIGH)
        GPIO.setup(self.__Datapin, GPIO.IN)

        while(GPIO.input(self.__Datapin)):
            time.sleep(0.001)
            if(GPIO.input(self.__Datapin)):
                GPIO.setup(self.__Datapin, GPIO.OUT)
                GPIO.output(self.__Datapin, GPIO.LOW)
                GPIO.setup(self.__Datapin, GPIO.IN)
        GPIO.setup(self.__Datapin, GPIO.OUT)

    def start(self):
        """send start signal to TM1637"""
        GPIO.output(self.__Clkpin, GPIO.HIGH)
        GPIO.output(self.__Datapin, GPIO.HIGH)
        GPIO.output(self.__Datapin, GPIO.LOW)
        GPIO.output(self.__Clkpin, GPIO.LOW)

    def stop(self):
        GPIO.output(self.__Clkpin, GPIO.LOW)
        GPIO.output(self.__Datapin, GPIO.LOW)
        GPIO.output(self.__Clkpin, GPIO.HIGH)
        GPIO.output(self.__Datapin, GPIO.HIGH)

    def br(self):
        """terse break"""
        self.stop()
        self.start()

    def coding(self, data):
        if(self.__doublePoint):
            pointData = 0x80
        else:
            pointData = 0

        if(data == 0x7F or data is None):
            data = 0
        else:
            data = HexDigits[data] + pointData
        return data

    def clock(self, military_time):
        """Clock script modified from: https://github.com/johnlr/raspberrypi-tm1637"""
        self.ShowDoublepoint(True)
        while (not self.__stop_event.is_set()):
            t = localtime()
            hour = t.tm_hour
            if not military_time:
                hour = 12 if (t.tm_hour % 12) == 0 else t.tm_hour % 12
            d0 = hour // 10 if hour // 10 else 36
            d1 = hour % 10
            d2 = t.tm_min // 10
            d3 = t.tm_min % 10
            digits = [d0, d1, d2, d3]
            self.Show(digits)
            # # Optional visual feedback of running alarm:
            # print digits
            # for i in tqdm(range(60 - t.tm_sec)):
            for i in range(60 - t.tm_sec):
                if (not self.__stop_event.is_set()):
                    time.sleep(1)

    def StartClock(self, military_time=True):
        # Stop event based on: http://stackoverflow.com/a/6524542/3219667
        self.__stop_event = threading.Event()
        self.__clock_thread = threading.Thread(
            target=self.clock, args=(military_time,))
        self.__clock_thread.start()

    def StopClock(self):
        try:
            print ('Attempting to stop live clock')
            self.__stop_event.set()
        except:
            print ('No clock to close')

def LCDOFF():
    display = TM1637(CLK=21, DIO=20, brightness=1.0)
    display.Clear()



#LEDNUMBER
def LCD_NUMBER(scrap1):
    display = TM1637(CLK=21, DIO=20, brightness=1.0)
    display.Clear()
    if int(scrap1) >= 1000 :
       splitx = list(str(scrap1))
       display.Show1(1, int(splitx[1]))
       display.Show1(2, int(splitx[2]))
       display.Show1(3, int(splitx[3]))
       display.Show1(0, int(splitx[0]))
       return True
    if int(scrap1) >= 100 :
       splitx = list(str(scrap1))
       display.Show1(1, int(splitx[0]))
       display.Show1(2, int(splitx[1]))
       display.Show1(3, int(splitx[2]))
    else:
        if int(scrap1) >= 10 :
         splitx = list(str(scrap1))
         display.Show1(2, int(splitx[0]))
         display.Show1(3, int(splitx[1]))
        else:
          display.Show1(3, int(scrap1))


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

if os.path.isfile('data.json'):
    with open('data.json', 'r') as f:
      json_data = json.load(f)
else:
    json_data = {"data":{"17":False,"22":False,"23":False,"27":False}}
    with open('data.json', 'w') as f:
      json.dump(json_data, f) 

def button_callback(channel):
    print(GPIO.input(channel))


@app.route('/')
def index():
    return render_template('index.html')

@socketio.event()
def my_event(message):
    emit('response', {'data': 'got it!'})

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
       if res["status"] == 'tm1637':
          json_data["data"]["tm1637"] = res["value"]
          LCD_NUMBER(res["value"])
          return send(update_data(json_data), broadcast=True)

       if res["status"] == 'start':
          if res['data'] == True :
             GPIO.setup(int(res['value']),GPIO.OUT)
          if res['data'] == False :
             GPIO.setup(int(res['value']),GPIO.IN)
          json_data["data"][str(res['value'])] = res["data"]
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