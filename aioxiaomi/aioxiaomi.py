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

PROPERTIES = ["power", "bg_power", "bright", "bg_bright", "nl_br", "ct", "bg_ct",
               "rgb", "bg_rgb", "hue", "bg_hue", "sat", "bg_sat", "color_mode","bg_lmode",
               "flowing", "bg_flowing", "flow_params", "bg_flow_params","music_on",
               "name", "delayoff",'fw_ver',"model","id"]

INT_PROPERTIES= ['bright', "bg_bright", "nl_br", "ct", "bg_ct", "rgb", "bg_rgb", "hue", "bg_hue", "sat", "bg_sat","delayoff"]
HEX_PROPERTIES= ["id"]

DEFAULT_TIMEOUT=0.5 # How long to wait for a response
DEFAULT_ATTEMPTS=1 # How many times to try

class Mode(IntEnum):
    Default = 0
    RGB = 1
    White = 2
    HSL = 3
    Flow = 4
    Night = 5
    Sleep = 7


class XiaomiConnect(aio.Protocol):
    """ This class is a single unicast connection to a Xiaomi device

        :param parent: The parent object. Must have register, unregister and data_received methods
        :type parent: object
    """

    def __init__(self, parent):
        self.parent = parent
        self.id = uuid4()
        self.last_sent = 0
    #
    # Protocol Methods
    #

    def connection_made(self, transport):
        """Method run when the connection to the lamp is established
        """
        self.transport = transport
        self.parent.register(self)

    def connection_lost(self):
        if self.parent:
            self.parent.unregister(self)

    def data_received(self,data):
        self.parent.data_received(data)

    def write(self,msg):
        self.transport.write((msg+"\r\n").encode())

    def close(self):
        self.transport.close()


class XiaomiBulb(object):
    """This correspond to a single light bulb.

    This handles all the communications with a single bulb. This is created upon
    discovery of the bulb.

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
        self.seq = ( self.seq + 1 ) % 256
        return self.seq

    async def try_sending(self,msg,timeout_secs=None, max_attempts=None):
        """Coroutine used to send message to the device when a response is needed.

        This coroutine will try to send up to max_attempts time the message, waiting timeout_secs
        for an answer. If no answer is received, it will consider that the device is no longer
        accessible and will unregister it.

            :param msg: The message to send
            :type msg: str
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

        attempts = 0
        while attempts < max_attempts:
            cid = msg['id']
            if cid not in self.pending_reply: return
            event = aio.Event()
            self.pending_reply[cid][0]= event
            attempts += 1
            myidx=self.tidx
            self.tidx = (self.tidx +1)%len(self.transports)
            print("Sending {}".format(msg))
            self.transports[myidx].write(json.dumps(msg))
            try:
                myresult = await aio.wait_for(event.wait(),timeout_secs)
                break
            except Exception as inst:
                if attempts >= max_attempts:
                    if msg['id'] in self.pending_reply:
                        callb =self.pending_reply[msg['id']][1]
                        if callb:
                            callb(self, None)
                    del(self.pending_reply[msg['id']])
                    #It's dead Jim
                    self.unregister(self)


    def send_msg(self,msg, callb=None, timeout_secs=None, max_attempts=None):
        """ Let's send
        """
        cid= self.seq_next()
        msg['id']=cid
        self.pending_reply[cid]=[None,callb]
        xxx=self.loop.create_task(self.try_sending(msg,timeout_secs, max_attempts))


    def data_received(self,data):
        #Do something
        #try:
        print("Received raw data: {}".format(data))
        received_data = json.loads(data)
        print("Received data: {}".format(received_data))
        if "id" in received_data:
            cid = int(received_data['id'])
            if cid in self.pending_reply:
                myevent,callb = self.pending_reply[cid]
                myevent.set()
                if callb:
                    callb(received_data)
                del(self.pending_reply[cid])

        elif 'method' in received_data:
            if received_data["method"] == "props":
                for prop,val in received_data["params"].items():
                    if prop in PROPERTIES:
                        self.properties[prop]=val

            self.default_callb(received_data["params"])
        #except:
            #pass



    def register_callback(self,callb):
        """Method used to register a default call back to be called when data is received

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
        for prop,val in zip(request,result):
            if prop in PROPERTIES:
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
                self.properties[p]

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

    def set_bright(self, brightness, effect="sudden", duration="100",callb=None):

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
            self.send_msg({ "method": "set_bright", "params": [bright, effect,duration] }, callb)
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

    #def set_music 1 ~ 3 int(action) string(host) int(port)

    def set_name(self, name, callb=None):

        """Set light name

            :param name:  New name
            :type name: str
            :param callb: a callback function. Given the list of values as parameters
            :type callb: callable
            :returns: None
            :rtype: None
        """
        if "set_name" in self.support:
            self.send_msg({ "method": "cron_add", "params": [name] },callb)
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
        print("Registering connection {} for {}".format(conn,self.bulb_id))
        if not self.registered:
            self.registered = True
            if self.parent:
                self.parent.register(self)

    def unregister(self,conn):
        """Proxy method to unregister the device with the parent.
        """
        print("Unregistering connection {} for {}".format(conn,self.bulb_id))
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

    #A couple of proxies
    @property
    def power(self):
        if "power" in self.properties:
            return  self.properties["power"]
        else:
            return None

    @property
    def colour(self):
        result = {"hue":None, "saturation": None, "value":None}
        if "sat" in self.properties:
            result['saturation']=self.properties["sat"]
        if "hue" in self.properties:
            result['hue']=self.properties["hue"]
        if "bright" in self.properties:
            result['value']=self.properties["bright"]

        return result

    @property
    def rgb(self):
        if "rgb" in self.properties:
            return  int(self.properties["rgb"])
        else:
            return 0

    @property
    def brightness(self):
        if "bright" in self.properties:
            return  int(self.properties["bright"])
        else:
            return 0

    @property
    def white(self):
        result = {"brightness":None, "temperature": None}
        if "ct" in self.properties:
            result['temperature']=self.properties["ct"]
        if "bright" in self.properties:
            result['brightness']=self.properties["bright"]

        return result

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
