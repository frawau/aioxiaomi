#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#
# This application is an example on how to use aiolifx
#
# Copyright (c) 2016 François Wautier
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
import sys
import asyncio as aio
import aioxioami as aiox
from functools import partial
import argparse
UDP_BROADCAST_PORT = 56700

#Simple bulb control from console
class bulbs():
    """ A simple class with a register and  unregister methods
    """
    def __init__(self):
        self.bulbs=[]
        self.pending_bulbs = []
        self.boi=None #bulb of interest

    def register(self,bulb):
        self.bulbs.append(bulb)
        self.bulbs.sort(key=lambda x: x.name or x.bulb_id )
        if opts.extra:
            bulb.register_callback(lambda y: print("Unexpected message: %s"%str(y)))
        try:
            self.pending_bulbs.remove(bulb)
        except:
            pass

    def unregister(self,bulb):
        idx=0
        for x in list([ y.bulb_id for y in self.bulbs]):
            if x == bulb.bulb_id:
                del(self.bulbs[idx])
                break
            idx+=1

    def new_bulb(self, sender, **kwargs):
        if 'id' in kwargs['headers']:
            found = False
            for abulb in self.bulbs:
                if abulb.bulb_id == kwargs['headers']:
                    found = True
                    break
            if not found:
                for abulb in self.pending_bulbs:
                    if abulb.bulb_id == kwargs['headers']:
                        found = True
                        break

            if not found:
                newbulb = aiox.XiaomiBulb(aio.get_event_loop(),kwargs['headers'],self)



def readin():
    """Reading from stdin and displaying menu"""

    selection = sys.stdin.readline().strip("\n")
    MyBulbs.bulbs.sort(key=lambda x: x.name or x.bulb_id)
    lov=[ x for x in selection.split(" ") if x != ""]
    if lov:
        if MyBulbs.boi:
            #try:
            if True:
                if int(lov[0]) == 0:
                    MyBulbs.boi=None
                elif int(lov[0]) == 1:
                    if len(lov) >1:
                        MyBulbs.boi.set_power(lov[1].lower())
                        MyBulbs.boi=None
                    else:
                        print("Error: For power you must indicate on or off\n")
                elif int(lov[0]) == 2:
                    if len(lov) >2:
                        try:
                            MyBulbs.boi.set_white_direct(
                                    min(100,int(round(float(lov[1])))),
                                    int(round(float(lov[2])))])

                            MyBulbs.boi=None
                        except:
                            print("Error: For white brightness (0-100) and temperature (1700-6500) must be numbers.\n")
                    else:
                        print("Error: For white you must indicate brightness (0-100) and temperature (1700-6500)\n")
                elif int(lov[0]) == 3:
                    if len(lov) >3:
                        try:
                            MyBulbs.boi.set_hsv_direct(min(359,int(round(float(lov[1])))),
                                    int(round(float(lov[2]))),
                                    int(round(float(lov[3]))))
                            MyBulbs.boi=None
                        except:
                            print("Error: For colour Red (0-255), Green (0-255) and Blue (0-255)) must be numbers.\n")
                    else:
                        print("Error: For colour you must indicate Red (0-255), Green (0-255) and Blue (0-255))\n")

                elif int(lov[0]) == 4:
                    print("Model: {}".format(boi.properties["model"]))
                    print("Name: {}".format(boi.name))
                    MyBulbs.boi=None
                elif int(lov[0]) == 5:
                    print("Firmware: {}".format(boi.properties["fw_ver"]))
                    MyBulbs.boi=None
                elif int(lov[0]) == 6:
                    if len(lov) >3:
                        try:
                            MyBulbs.boi.start_cf(10,"start",[100,aiox.Mode.RGB.value,int(round(float(lov[1])*65535.0+float(lov[2])*256+float(lov[3]))),MyBulbs.boi.brightness,100,,aiox.Mode.RGB.value,MyBulbs.boi.rgb,MyBulbs.boi.brightness])
                            MyBulbs.boi=None
                        except:
                            print("Error: For pulse hue (0-360), saturation (0-100) and brightness (0-100)) must be numbers.\n")
                    else:
                        print("Error: For pulse you must indicate hue (0-360), saturation (0-100) and brightness (0-100))\n")
            #except:
                #print ("\nError: Selection must be a number.\n")
        else:
            try:
                if int(lov[0]) > 0:
                    if int(lov[0]) <=len(MyBulbs.bulbs):
                        MyBulbs.boi=MyBulbs.bulbs[int(lov[0])-1]
                    else:
                        print("\nError: Not a valid selection.\n")

            except:
                print ("\nError: Selection must be a number.\n")

    if MyBulbs.boi:
        print("Select Function for {}:".format(MyBulbs.boi.name))
        print("\t[1]\tPower (0 or 1)")
        print("\t[2]\tWhite (Brigthness Temperature)")
        print("\t[3]\tColour (Red Green Blue)")
        print("\t[4]\tInfo")
        print("\t[5]\tFirmware")
        print("\t[6]\tPulse")
        print("")
        print("\t[0]\tBack to bulb selection")
    else:
        idx=1
        print("Select Bulb:")
        for x in MyBulbs.bulbs:
            print("\t[{}]\t{}".format(idx,x.name or x.bulb_id))
            idx+=1
    print("")
    print("Your choice: ", end='',flush=True)

def handler(sender, **kwargs):
    if 'id' in kwargs['headers']:


parser = argparse.ArgumentParser(description="Track and interact with Lifx light bulbs.")
parser.add_argument("-6", "--ipv6prefix", default=None,
                    help="Connect to Lifx using IPv6 with given /64 prefix (Do not end with colon unless you have less than 64bits).")
parser.add_argument("-x","--extra", action='store_true', default=False,
                    help="Print unexpected messages.")
try:
    opts = parser.parse_args()
except Exception as e:
    parser.error("Error: " + str(e))



MyBulbs= bulbs()
loop = aio.get_event_loop()
coro = aiox.start_discovery(MyBulbs.new_bulb)
transp, server = loop.run_until_complete(coro)
try:
    loop.add_reader(sys.stdin,readin)
    server.broadcast(2)
    print("Hit \"Enter\" to start")
    print("Use Ctrl-C to quit")
    loop.run_forever()
except:
    pass
finally:
    server.cancel()
    loop.remove_reader(sys.stdin)
    loop.close()
