#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# This library is an asyncio library to communicate with Xiaomi Yeelight
# LED lights.
#
# Copyright (c) 2017 François Wautier
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies
# or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR
# IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE

import asyncio as aio
import json
from functools import partial
from enum import IntEnum
from uuid import uuid4
import datetime as dt
from random import randint
import socket

PROPERTIES = ["power", "bg_power", "bright", "bg_bright", "nl_br", "ct", "bg_ct",
               "rgb", "bg_rgb", "hue", "bg_hue", "sat", "bg_sat", "color_mode","bg_lmode",
               "flowing", "bg_flowing", "flow_params", "bg_flow_params","music_on",
               "name", "delayoff",'fw_ver',"model","id"]

INT_PROPERTIES= ['bright', "bg_bright", "nl_br", "ct", "bg_ct", "rgb", "bg_rgb", "hue", "bg_hue", "sat", "bg_sat","delayoff", 'color_mode']
HEX_PROPERTIES= ["id"]

DEFAULT_TIMEOUT=0.5 # How long to wait for a response
DEFAULT_ATTEMPTS=1 # How many times to try
MESSAGE_WINDOW = 256

class Mode(IntEnum):
    Default = 0
    RGB = 1
    White = 2
    HSV = 3
    Flow = 4
    Night = 5
    Sleep = 7


class Queue(object):
    """A simple queue implementation. Very basic

    """
    def __init__(self):
        self.queue=[]

    def get(self):
        try:
            v = self.queue[0]
            self.queue= self.queue[1:]
            return v
        except:
            return None

    def put(self,x):
        self.queue.append(x)

    def retrieve(self,idx):
        if idx < len(self.queue):
            v = self.queue[idx]
            self.queue = self.queue[:idx]+self.queue[idx+1:]
            return v
        else:
            return None

    def empty(self):
        return len(self.queue)==0

    def trim(self,length):
        self.queue = self.queue[0-length:]

    def __len__(self):
        return len(self.queue)


class XiaomiMusicConnect(aio.Protocol):
    """This class is a single server connection to a Xiaomi device

        :param parent: The parent object. Must have register, unregister and data_received methods
        :type parent: object
        :param future: A future object, set when connection is made
        :type future: aio.Future
        :param autoclose: Indicate how long (in secs) to idle before cancelling the music mode. If 0
                          the music mode must be explicitly stopped.
        :type autoclose: float
    """

    def __init__(self, parent, future,autoclose=0):
        self.parent = parent
        self.future = future
        self.autoclose = autoclose
        self.transport = None
        self.last_sent = dt.datetime.now()
        #print("Music Mode Server Created")
    #
    # Protocol Methods
    #

    def connection_made(self, transport):
        """Method run when the connection to the lamp is established
        """

        #print("Got connection from {}".format(transport.get_extra_info('peername')))
        self.transport = transport
        self.future.set_result(self)
        if self.autoclose:
            xx = self.parent.loop.create_task(self._autoclose_me())

    def connection_lost(self, error):
        self.parent.music_mode_off()

    def data_received(self,data):
        #self.parent.data_received(data)
        #print("MUSIC Received {}".format(data)) #Are we supposed to receive something?
        pass

    def write(self,msg):
        #print("Music Sending {}".format(msg))
        self.last_sent = dt.datetime.now()
        self.transport.write((msg+"\r\n").encode())

    def close(self):
        self.transport.close()

    async def _autoclose_me(self):
        while True:
            if dt.datetime.now()-self.last_sent > dt.timedelta(seconds=self.autoclose):
                #print("Time to cleanup")
                self.close()
                return
            await aio.sleep(1)

class XiaomiConnect(aio.Protocol):
    """ This class is a single unicast connection to a Xiaomi device

        :param parent: The parent object. Must have register, unregister and data_received methods
        :type parent: object
    """

    def __init__(self, parent):
        self.parent = parent
        self.id = uuid4()
        self.last_sent = dt.datetime.now() - dt.timedelta(seconds=2)
        self.ip_addr = ""
    #
    # Protocol Methods
    #

    def connection_made(self, transport):
        """Method run when the connection to the lamp is established
        """
        self.transport = transport
        self.parent.register(self)

    def connection_lost(self, error):
        if self.parent:
            self.parent.unregister(self)

    def data_received(self,data):
        self.parent.data_received(data)

    def write(self,msg):
        #print("Sending {}".format(msg))
        self.last_sent = dt.datetime.now()
        self.transport.write((msg+"\r\n").encode())

    def close(self):
        self.transport.close()


class XiaomiBulb(object):
    """This correspond to a single light bulb.

    This handles all the communications with a single bulb. This is created upon
    discovery of the bulb.from queue import Queue


        :param loop: The async loop being used
        :type loop: asyncio.EventLoop
        :param headers: A dictionary received upon discovery
        :type headers: dict
        :param parent: Parent object with register/unregister methods
        :type parent: object
        :param tnb: The number of connections to establish with the bulb (default 1)
        :type tnb: int

     """


    def __init__(self, loop, headers, parent=None, tnb=1):
        self.loop = loop
        self.parent = parent
        self.support = headers["support"]
        self.properties = {}
        for key in headers:
            if key in PROPERTIES:
                if key in INT_PROPERTIES:
                    self.properties[key]=int(headers[key])
                elif key in HEX_PROPERTIES:
                    self.properties[key]=int(headers[key],base=16)
                else:
                    self.properties[key]=headers[key]
        self.ip_address = headers["location"].split("://")[1].split(":")[0]
        self.port = headers["location"].split("://")[1].split(":")[1]
        self.seq = 0
        # Key is the message sequence, value is a callable
        self.pending_reply = {}
        self.tnb = max(1,min(4,tnb)) #Minimum 1, max 4 per Xiaomi specs
        self.transports = []
        self.tidx = 0
        self.musicm = False
        self.timeout_secs = DEFAULT_TIMEOUT
        self.default_attempts = DEFAULT_ATTEMPTS
        self.default_callb = lambda x: None
        self.registered = False
        self.message_queue=Queue()
        self.queue_limit = 0 #No limit
        self.queue_policy = "drop" #What to do when limit is reached
        self.is_sending = False
        self.my_ip_addr = ""

    def activate(self):
        #Start the transports
        for x in range(self.tnb):
            listen = self.loop.create_connection(
                    partial(XiaomiConnect,self),
                        self.ip_address,self.port)
            xx = aio.ensure_future(listen)

    def seq_next(self):
        """Method to return the next sequence value to use in messages.

            :returns: next number in sequensce (modulo 128)
            :rtype: int
        """
        self.seq = ( self.seq + 1 ) % MESSAGE_WINDOW
        return self.seq

    async def try_sending(self,timeout_secs=None, max_attempts=None):
        """Coroutine used to send message to the device when a response is needed.

        This coroutine will try to send up to max_attempts time the message, waiting timeout_secs
        for an answer. If no answer is received, it will consider that the device is no longer
        accessible and will unregister it.

            :param timeout_secs: Number of seconds to wait for a response
            :type timeout_secs: int
            :param max_attempts: .
            :type max_attempts: int
            :returns: a coroutine to be scheduled
            :rtype: coroutine
        """
        if timeout_secs is None:
            timeout_secs = DEFAULT_TIMEOUT
        if max_attempts is None:
            max_attempts = DEFAULT_ATTEMPTS
        mydelta=dt.timedelta(seconds=1)
        dodelay = len(self.transports)-1
        while not self.message_queue.empty():
            callb,msg = self.message_queue.get()
            if self.musicm:
                if isinstance(self.musicm,aio.Future):
                    #print("Awaiting Future {}".format(self.musicm))
                    try:
                        x=await aio.wait_for(self.musicm,timeout=2)
                        self.musicm = self.musicm.result()
                    except:
                        #Oops
                        self.musicm = False
                        #print("Future Failed")
                        self.message_queue.trim(self.queue_limit)
                        continue #We just drop the extra messages
                    #print("Future gave {}".format(self.musicm))
                self.musicm.write(json.dumps(msg))
                if callb:
                    callb({"id":msg["id"], "result":["ok"]})
                if self.message_queue.empty():
                    await aio.sleep(0.1)
            else:
                attempts = 0
                while attempts < max_attempts:
                    now = dt.datetime.now()
                    cid = msg['id']
                    event = aio.Event()
                    self.pending_reply[cid]= [event, callb]
                    attempts += 1
                    myidx=self.tidx
                    self.tidx = (self.tidx +1)%len(self.transports)
                    diff = now - self.transports[myidx].last_sent
                    if diff < mydelta:
                        await aio.sleep((mydelta-diff).total_seconds())
                    self.transports[myidx].write(json.dumps(msg))
                    try:
                        myresult = await aio.wait_for(event.wait(),timeout_secs)
                        break
                    except Exception as inst:
                        if attempts >= max_attempts:
                            if cid in self.pending_reply:
                                callb =self.pending_reply[cid][1]
                                if callb:
                                    callb( None)
                                del(self.pending_reply[cid])
                            #It's dead Jim
                            self.unregister(self.transports[myidx])
                            if len(self.transports) == 0:
                                self.is_sending = False
                                return
                if dodelay:
                    dodelay -= 1
                    await aio.sleep(1.0/len(self.transports))
        self.is_sending = False

    def send_msg_noqueue(self,msg, callb=None):
        """Sending a message by-passing the queue
        """
        cid= self.seq_next()
        msg['id']=cid
        if callb:
            self.pending_reply[cid]= [None, callb]
        self.transports[0].write(json.dumps(msg))

    def send_msg(self,msg, callb=None, timeout_secs=None, max_attempts=None):
        """ Let's send
        """
        if self.queue_limit == 0 or len(self.message_queue)< self.queue_limit:
            cid= self.seq_next()
            msg['id']=cid
            self.message_queue.put((callb,msg))
            if not self.is_sending:
                self.is_sending = True
                xxx=self.loop.create_task(self.try_sending(timeout_secs, max_attempts))
        elif self.queue_limit > 0:
            if self.queue_policy != "drop":
                cid= self.seq_next()
                msg['id']=cid
                self.message_queue.put((callb,msg))
                if self.queue_policy == "head":
                    x=self.message_queue.get()
                    del(x)
                elif self.queue_policy == "adapt":
                    self.set_music("start",5)
                else :#self.queue_policy == "random":
                    idx = randint(0,len(self.message_queue)-1)
                    x=self.message_queue.retrieve(idx)
                    del(x)

    def data_received(self,data):
        #Do something
        try:
            #print("Received raw data: {}".format(data))
            received_data = json.loads(data)
            if "id" in received_data:
                cid = int(received_data['id'])
                if cid in self.pending_reply:
                    myevent,callb = self.pending_reply[cid]
                    if myevent:
                        myevent.set()
                    if callb:
                        callb(received_data)
                    del(self.pending_reply[cid])

            if 'method' in received_data:
                if received_data["method"] == "props":
                    for prop,val in received_data["params"].items():
                        if prop in PROPERTIES:
                            self.properties[prop]=val

                self.default_callb(received_data["params"])
        except:
            pass



    def register_callback(self,callb):
        """Method used to register a default call back to be called when data is received

        The callback will be called with a yeelight response.

            :param callb: The calllback to be executed.
            :type callb: callable

        """
        self.default_callb = callb

    #
    # Xiaomi method
    #

    def get_prop(self, props, callb=None):
        """Get current values of light properties

            :param props:  list of properties
            :type props: list
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: True if supported, False if not
            :rtype: bool
        """
        if "get_prop" in self.support:
            self.send_msg({"method":"get_prop","params":props},partial(self._get_prop_reply,props,callb))
            return True
        return False


    def _get_prop_reply(self, request, callb, result):
        """Get current values of light properties

        :param props:  list of properties
        :type props: list
        """
        #print("\n\nXIAOMI For {} got {}\n\n".format(request,result))
        if "result" in result:
            for prop,val in zip(request,result["result"]):
                if prop in PROPERTIES:
                    if prop in INT_PROPERTIES:
                        self.properties[prop]=int(val)
                    elif prop in HEX_PROPERTIES:
                        self.properties[prop]=int(val,base=16)
                    else:
                        self.properties[prop]=val
            if callb:
                callb(result)

    def _cmd_reply(self,props,callb,result):
        """Generic command result.

            :param props: A dictionary of properties affected by the command with
                          their value
            :type props: dict
            :param reply" Result of command "ok" or not
            :param callb: Callback
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "ok" in result:
            for p,v in props.items():
                self.properties[p]=v

        if callb:
            callb(result)

    def set_temperature(self, temp, effect="sudden", duration="100",callb=None):
        """Set temperature of light

            :param temp:  Temperature in K (1700 - 6500 K)
            :type temp: int
            :param effect: One of "smooth" or "suddent"
            :type effect: str
            :param duration: "smooth" effect duration in millisecs
            :type duration: int
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if self.properties["power"] == "on" and "set_ct_abx" in self.support:
            if effect == "smooth":
                duration = max(30,duration) #Min is 30 msecs
            self.send_msg({ "method": "set_ct_abx", "params": [temp, effect,duration]},callb)
            return True
        return False

    def set_rgb(self, rgb, effect="sudden", duration="100",callb=None):

        """Set colour of light

            :param rgb:  RGB as int
            :type rgb: int
            :param effect: One of "smooth" or "suddent"
            :type effect: str
            :param duration: "smooth" effect duration in millisecs
            :type duration: int
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if self.properties["power"] == "on" and "set_rgb" in self.support:
            cid= self.seq_next()
            if effect == "smooth":
                duration = max(30,duration) #Min is 30 msecs
            self.send_msg({ "method": "set_rgb", "params": [rgb, effect,duration]}, callb)
            return True
        return False

    def set_hsv(self, hue, sat, effect="sudden", duration="100",callb=None):

        """Set colour of light

            :param hue:  hue as int (0-359)
            :type hue: int
            :param sat:  saturation as int (0-sat)
            :type sat: int
            :param effect: One of "smooth" or "suddent"
            :type effect: str
            :param duration: "smooth" effect duration in millisecs
            :type duration: int
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if self.properties["power"] == "on" and "set_hsv" in self.support:
            if effect == "smooth":
                duration = max(30,duration) #Min is 30 msecs
            self.send_msg({ "method": "set_hsv", "params": [hue, sat, effect,duration] }, callb)
            return True
        return False

    def set_brightness(self, brightness, effect="sudden", duration="100",callb=None):

        """Set brightness of light

            :param brightness:  brightness as int (0-100)
            :type brightness: int
            :param effect: One of "smooth" or "suddent"
            :type effect: str
            :param duration: "smooth" effect duration in millisecs
            :type duration: int
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if self.properties["power"] == "on" and "set_bright" in self.support:
            if effect == "smooth":
                duration = max(30,duration) #Min is 30 msecs
                self.send_msg({ "method": "set_bright", "params": [brightness, effect,duration] }, callb)
            return True
        return False

    def set_power(self, power, effect="sudden", duration="100",mode=None,callb=None):

        """Set power of light

            :param power:  Power mode ("on" or "off")
            :type power: str
            :param effect: One of "smooth" or "suddent"
            :type effect: str
            :param duration: "smooth" effect duration in millisecs
            :type duration: int
            :param mode: Mode (from class Mode) to switch to
            :type mode: Mode
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "set_power" in self.support:
            if effect == "smooth":
                duration = max(30,duration) #Min is 30 msecs
            if mode:
                self.send_msg({ "method": "set_power", "params": [power, effect,duration,mode] },callb)
            else:
                self.send_msg({ "method": "set_power", "params": [power, effect,duration] },callb)
            return True
        return False


    def set_default (self,callb=None):

        """Save current state as default

            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "set_default" in self.support:
            self.send_msg({ "method": "set_default", "params": []},callb)
            return True
        return False

    def bg_set_temperature(self, temp, effect="sudden", duration="100",callb=None):
        """Set temperature of light

            :param temp:  Temperature in K (1700 - 6500 K)
            :type temp: int
            :param effect: One of "smooth" or "suddent"
            :type effect: str
            :param duration: "smooth" effect duration in millisecs
            :type duration: int
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if self.properties["power"] == "on" and "bg_set_ct_abx" in self.support:
            if effect == "smooth":
                duration = max(30,duration) #Min is 30 msecs
            self.send_msg({ "method": "bg_set_ct_abx", "params": [temp, effect,duration]},callb)
            return True
        return False

    def bg_set_rgb(self, rgb, effect="sudden", duration="100",callb=None):

        """Set colour of light

            :param rgb:  RGB as int
            :type rgb: int
            :param effect: One of "smooth" or "suddent"
            :type effect: str
            :param duration: "smooth" effect duration in millisecs
            :type duration: int
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if self.properties["power"] == "on" and "bg_set_rgb" in self.support:
            if effect == "smooth":
                duration = max(30,duration) #Min is 30 msecs
            self.send_msg({ "method": "set_rgb", "params": [rgb, effect,duration] },callb)
            return True
        return False

    def bg_set_hsv(self, hue, sat, effect="sudden", duration="100",callb=None):

        """Set colour of light

            :param hue:  hue as int (0-359)
            :type hue: int
            :param sat:  saturation as int (0-sat)
            :type sat: int
            :param effect: One of "smooth" or "suddent"
            :type effect: str
            :param duration: "smooth" effect duration in millisecs
            :type duration: int
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if self.properties["power"] == "on" and "bg_set_hsv" in self.support:
            if effect == "smooth":
                duration = max(30,duration) #Min is 30 msecs
            self.send_msg({ "method": "bg_set_hsv", "params": [hue, sat, effect,duration] },callb)
            return True
        return False


    def toggle (self,callb=None):

        """Toggle power of light

            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "toggle" in self.support:
            self.send_msg({ "method": "toggle", "params": []},callb)
            return True
        return False

    def bg_toggle (self,callb=None):

        """Toggle power of bg light

            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "bg_toggle" in self.support:
            self.send_msg({ "method": "bg_toggle", "params": []},callb)
            return True
        return False

    def dev_toggle (self,callb=None):

        """Toggle power of light and bg light

            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "bg_toggle" in self.support:
            self.send_msg({ "method": "bg_toggle", "params": []},callb)
            return True
        return False

    def start_flow(self,count, endstate, flex, callb=None):

        """Set colour flow of light

            :param count: How many times is the flex to be ran. 0 means forever.
            :type count: integers
            :param endstate: What should be the state of the light at the end:
                                "start" same state as it was at the start of the flow
                                "stop" stay in the end state
                                "off" Light should be off at the end
            :param flex:  A list of transitions describing the flow expression. The list contains a
                          multiple of 4 of integers. Each set of 4 represents one effect. The 4 numbers are:
                                duration in msec
                                mode Mode.RGB.value, Mode.White.value or Mode.Sleep.value
                                value  the value  rgb or temperature
                                brightness: the brightness

            :type flex: list
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if self.properties["power"] == "on" and "start_cf" in self.support:
            self.send_msg({ "method": "start_cf", "params": [count, ["start","stop","off"].index(endstate.lower()),",".join(map(str,flex))] },callb)
            return True
        return False


    def stop_flow(self,callb=None):

        """Stop a flow running on the light

            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "stop_cf" in self.support:
            self.send_msg({ "method": "stop_cf", "params": []},callb)
            return True
        return False


    def set_rgb_direct(self, rgb, brightness, callb=None):

        """Set colour of light

            :param rgb:  RGB as int
            :type rgb: int
            :param brightness: The brightness
            :type brightness: int
            :returns: None
            :rtype: None
        """
        if "set_scene" in self.support:
            self.send_msg({ "method": "set_scene", "params": ["color", rgb, brightness] }, callb)
            return True
        return False

    def set_hsv_direct(self, hue, sat, brightness, callb=None):

        """Set colour of light

            :param hue:  hue as int (0-359)
            :type hue: int
            :param sat:  saturation as int (0-sat)
            :type sat: int
            :param brightness: The brightness
            :type brightness: int
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "set_scene" in self.support:
            self.send_msg({ "method": "set_scene", "params": ["hsv", hue, sat, brightness] },callb)
            return True
        return False

    def set_white_direct(self, temperature, brightness,callb=None):

        """Set temperature and brightness of light

            :param temperature:  Lamp colour temperature
            :type temperature: int
            :param brightness: The brightness
            :type brightness: int
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "set_scene" in self.support:
            self.send_msg({ "method": "set_scene", "params": ["ct", temperature, brightness] },callb)
            return True
        return False

    def set_flow_direct(self, count, endstate, flex,callb=None):
        """Set colour flow of light

            :param count: How many times is the flex to be ran. 0 means forever.
            :type count: integers
            :param endstate: What should be the state of the light at the end:
                                "start" same state as it was at the start of the flow
                                "stop" stay in the end state
                                "off" Light should be off at the end
            :param flex:  A list of transitions describing the flow expression. The list contains a
                          multiple of 4 of integers. Each set of 4 represents one effect. The 4 numbers are:
                                duration in msec
                                mode Mode.RGB.value, Mode.White.value or Mode.Sleep.value
                                value  the value  rgb or temperature
                                brightness: the brightness

            :type brightness: list
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """

        if "set_scene" in self.support:
            self.send_msg({ "method": "set_scene", "params": ["cf", count, ["start","stop","off"].index(endstate.lower()),flex] },callb)
            return True
        return False

    def set_timed_power(self, brightness, delay, callb=None):

        """Set temperature and brightness of light

            :param temperature:  Lamp colour temperature
            :type temperature: int
            :param brightness: The brightness
            :type brightness: int
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "set_scene" in self.support:
            self.send_msg({ "method": "set_scene", "params": ["auto_delay_off", brightness, delay] },callb)
            return True
        return False

    def cron_add(self,action,delay, callb=None):

        """Set an action with a delay

            :param action:  Currently only "off"
            :type action: str
            :param delay: delay in minutes
            :type delay: int
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if self.properties["power"] == "on" and "cron_add" in self.support:
            self.send_msg({ "method": "cron_add", "params": [["off","on"].index(action.lower()),delay] },callb)
            return True
        return False

    def cron_del(self,action, callb=None):

        """Cancel a timed action

            :param action:  Currently only "off"
            :type action: str
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if self.properties["power"] == "on" and "cron_del" in self.support:
            self.send_msg({ "method": "cron_del", "params": [["off","on"].index(action.lower())] },callb)
            return True
        return False

    def cron_get(self,action, callb=None):

        """Cancel a timed action

            :param action:  Currently only "off"
            :type action: str
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if self.properties["power"] == "on" and "cron_get" in self.support:
            self.send_msg({ "method": "cron_get", "params": [["off","on"].index(action.lower())] },callb)
            return True
        return False

    #TODO implement these
    #def set_adjust 2 string(action) string(prop)

    def set_music (self,action, delay=5.0, callb=None):

        """Start music mode.

        Before starting the music mode, one must setup a server
        waiting at host:port

            :param action: start or stop
            :type action: str
            :param delay: Idle delay before closing
            :type delay: float
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "set_music" in self.support:

            if action.lower() =="start" and not self.musicm:
                while True:
                    try:
                        myport = randint(9000, 24376)
                        sock = socket.socket()
                        sock.bind((self.my_ip_addr,myport)) #Make sure the port is free
                        break
                    except:
                        pass
                self.musicm = aio.Future()
                #print("Start Future {}".format(self.musicm))
                coro=self.loop.create_server(partial(XiaomiMusicConnect,self,self.musicm,delay), sock=sock)
                xx = aio.ensure_future(coro)
                #self.loop.call_soon(self.set_music,"start",self.my_ip_addr,myport)
                self.loop.call_soon(self.send_msg_noqueue,{ "method": "set_music", "params": [["stop","start"].index(action.lower()),self.my_ip_addr,myport] },callb)
            elif action.lower() == "stop" and self.musicm:
                self.loop.call_soon(self.send_msg_noqueue,{ "method": "set_music", "params": [["stop","start"].index(action.lower())] },callb)
                self.music_mode_off()
            else:
                return False
            return True
        return False

    def set_name(self, name, callb=None):

        """Set light name

            :param name:  New name
            :type name: str
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "set" in self.support:
            self.send_msg({ "method": "set_name", "params": [name] },callb)
            return True
        return False


    #
    # Management Methods
    def register(self, conn):
        """A connection is registering
            return True
        return False
        """
        self.transports.append(conn)
        #print("Registering connection {} for {}".format(conn,self.bulb_id))
        if not self.registered:
            self.my_ip_addr = conn.transport.get_extra_info('sockname')[0]
            self.registered = True
            if self.parent:
                self.parent.register(self)

    def unregister(self,conn):
        """Proxy method to unregister the device with the parent.
        """
        #print("Unregistering connection {} for {}".format(conn,self.bulb_id))
        for x in range(len(self.transports)):
            if self.transports[x].id == conn.id:
                del(self.transports[x])
                break

        if len(self.transports)==0 and self.registered:
            #Only if we have not received any message recently.
            #if datetime.datetime.now()-datetime.timedelta(seconds=self.unregister_timeout) > self.lastmsg:
            self.registered = False
            if self.parent:
                self.parent.unregister(self)

    def cleanup(self):
        """Method to call to cleanly terminate the connection to the device.
        """
        for x in self.tranports:
            x.close()

    def set_connections(self,nb):
        """Function to set the number of connection to open to a single bulb.

        By default, Xiaomi limits to 1 command per second per channel. You can
        increase that by opening more channels. In any case, the overall limit is 144
        commands per seconds, so more than 2 will create issues. This MUST be used before
        the bulb is activated. After that it has no effect.

        :param nb: The number of channels to open 1 to 4
        :type nb: int
        """
        self.tnb = nb

    def set_queue_limit(self,length,policy="drop"):
        """Set the queue size limit and the policy, what to do when the size limit is reached

            :param length: The maximum length of the message sending queue. 0 means no limit
            :type length: int
            :param policy: What to do when the queue size limit is reached. Values can be:
                    drop: drop the extra messages
                    head: drop the head of the queu
                    random: drop a random message in the queue
                    adapt: switch to "music" mode and send
        """
        self.queue_limit = length
        self.queue_policy = policy

    def music_mode_off(self):
        if self.musicm:
            #self.musicm is set to XiaomiMusicConnect in try_sending. So if we stop without sending, we need to check.
            if isinstance(self.musicm,aio.Future):
                if not self.musicm.cancel():
                    try:
                        self.musicm.result().close()
                    except:
                        pass
            else:
                self.musicm.close()
            self.musicm = False

    #A couple of proxies
    @property
    def power(self):
        if "power" in self.properties:
            return  self.properties["power"]
        else:
            return "off"

    @property
    def colour(self):
        result = {"hue":0, "saturation": 0, "brightness":0}
        if "sat" in self.properties:
            result['saturation']=self.properties["sat"]
        if "hue" in self.properties:
            result['hue']=self.properties["hue"]
        if "bright" in self.properties:
            result['brightness']=self.properties["bright"]

        return result

    @property
    def rgb(self):
        result = {"red":0, "green": 0, "blue":0}
        if "rgb" in self.properties:
            val=int(self.properties["rgb"])
            for col in ["blue","green","red"]:
                result[col] = val%256
                val=int((val-result[col])/256)

            return  int(self.properties["rgb"])
        else:
            return result

    @property
    def brightness(self):
        if "bright" in self.properties:
            return  int(self.properties["bright"])
        else:
            return 0

    @property
    def white(self):
        result = {"brightness":0, "temperature": 0}
        if "ct" in self.properties:
            result['temperature']=self.properties["ct"]
        if "bright" in self.properties:
            result['brightness']=self.properties["bright"]

        return result

    @property
    def current_colour(self):
        if self.properties['color_mode'] == Mode.RGB.value:
            return self.rgb
        elif self.properties['color_mode'] == Mode.HSV.value:
            return self.colour
        else:
            return self.white

    @property
    def name(self):
        if "name" in self.properties:
            return  self.properties["name"]
        else:
            return None

    @property
    def bulb_id(self):
        if "id" in self.properties:
            return  self.properties["id"]
        else:
            return None
