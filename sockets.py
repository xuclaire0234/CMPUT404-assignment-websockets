#!/usr/bin/env python
# coding: utf-8
# Copyright (c) 2013-2014 Abram Hindle
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import flask
from flask import Flask, request, Response, redirect, jsonify
from flask_sockets import Sockets
import gevent
from gevent import queue
import time
import json
import os

app = Flask(__name__)
sockets = Sockets(app)
app.debug = True

# reference:
# https://github.com/abramhindle/WebSocketsExamples/blob/master/chat.py
class Client:
    def __init__(self):
        self.queue = queue.Queue()

    def put(self, v):
        self.queue.put_nowait(v)

    def get(self):
        return self.queue.get()

class World:
    def __init__(self):
        self.clear()
        # we've got listeners now!
        self.listeners = list()
        
    def add_set_listener(self, listener):
        self.listeners.append( listener )

    def update(self, entity, key, value):
        entry = self.space.get(entity,dict())
        entry[key] = value
        self.space[entity] = entry
        self.update_listeners( entity )

    def set(self, entity, data):
        self.space[entity] = data
        self.update_listeners( entity )

    def update_listeners(self, entity):
        '''update the set listeners'''
        for listener in self.listeners:
            listener(entity, self.get(entity))

    def clear(self):
        self.space = dict()

    def get(self, entity):
        return self.space.get(entity,dict())
    
    def world(self):
        return self.space
# reference:
# https://github.com/abramhindle/WebSocketsExamples/blob/master/chat.py
myWorld = World()
clients = list()   

def send_all(msg):
    for client in clients:
        client.put( msg )

def send_all_json(obj):
    send_all( json.dumps(obj) )    


def set_listener(entity, data):
    ''' do something with the update ! '''
    """Send the updated entity data to all connected clients."""
    message = json.dumps({entity: data})
    send_message_to_all_clients(message)

def send_message_to_all_clients(message):
    """Send a message to all connected clients."""
    for client in clients:
        client.put(message)

myWorld.add_set_listener( set_listener )
        
@app.route('/')
def hello():
    return flask.redirect("/static/index.html")

# reference:
# https://github.com/abramhindle/WebSocketsExamples/blob/master/chat.py
def read_ws(ws,client):
    '''A greenlet function that reads from the websocket'''
    try:
        while True:
            msg = ws.receive()
            print("WS RECV: %s" % msg)
            if msg is not None:
                packet = json.loads(msg)
                entity = next(iter(packet))  # Get the first key in the packet
                data = packet[entity]

                myWorld.set(entity, data)  # Update the myWorld object with the received data
                send_all_json(packet)
            else:
                break
    except:
        '''Done'''

# reference:
# https://github.com/abramhindle/WebSocketsExamples/blob/master/chat.py
@sockets.route('/subscribe')
def subscribe_socket(ws):
    client = Client()
    clients.append(client)
    g = gevent.spawn( read_ws, ws, client )  
    # send the current world state to a newly connected client when they subscribe to the WebSocket.   
    ws.send(json.dumps(myWorld.world()))
    try:
        while True:
            # block here
            msg = client.get()
            ws.send(msg)
    except Exception as e:# WebSocketError as e:
        print( "WS Error %s" % e)
    finally:
        clients.remove(client)
        gevent.kill(g)

# I give this to you, this is how you get the raw body/data portion of a post in flask
# this should come with flask but whatever, it's not my project.
def flask_post_json():
    '''Ah the joys of frameworks! They do so much work for you
       that they get in the way of sane operation!'''
    if (request.json != None):
        return request.json
    elif (request.data != None and request.data.decode("utf8") != u''):
        return json.loads(request.data.decode("utf8"))
    else:
        return json.loads(request.form.keys()[0])

@app.route("/entity/<entity>", methods=['POST', 'PUT'])
def update(entity):
    '''update the entities via this interface'''
    data = request.get_json()
    if data is not None:
        for key, value in data.items():
            myWorld.update(entity, key, value)
        # Notify all connected WebSocket clients of the update
        send_all_json({entity: myWorld.get(entity)})
        return jsonify(data), 200
    else:
        return jsonify({"error": "Invalid JSON data"}), 400
    
@app.route("/world", methods=['POST','GET'])    
def world():
    '''you should probably return the world here'''
    return jsonify(myWorld.world()) 

@app.route("/entity/<entity>")    
def get_entity(entity):
    '''This is the GET version of the entity interface, return a representation of the entity'''
    return jsonify(myWorld.get(entity))

@app.route("/clear", methods=['POST','GET'])
def clear():
    '''Clear the world out!'''
    myWorld.clear()
    return jsonify(myWorld.world()) # 

if __name__ == "__main__":
    ''' This doesn't work well anymore:
        pip install gunicorn
        and run
        gunicorn -k flask_sockets.worker sockets:app
    '''
    app.run()