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
import aioxiaomi as aiox
from functools import partial
import argparse
from random import randint

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
        #print("Adding bulb {} {} {}".format(bulb,bulb.name,bulb.bulb_id))
        self.bulbs.append(bulb)
        self.bulbs.sort(key=lambda x: x.name or str(x.bulb_id) )
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

    def new_bulb(self, address, headers):
        newbulb = aiox.XiaomiBulb(aio.get_event_loop(),headers,self)
        found = False
        for abulb in self.bulbs:
            if abulb.bulb_id == newbulb.bulb_id:
                found = True
                break
        if not found:
            for abulb in self.pending_bulbs:
                if abulb.bulb_id == newbulb.bulb_id:
                    found = True
                    break

        if not found:
            #print("Activating bulb {} with id {}".format(newbulb,newbulb.bulb_id))
            self.pending_bulbs.append(newbulb)
            newbulb.set_connections(2) #Open 2 channels to the bulb
            newbulb.set_queue_limit(5,"adapt")
            newbulb.activate()
        else:
            del(newbulb)


async def flood_weelight(light, count):
    for x in range(0,count):
        thiscol = randint(0,16777215)
        light.set_rgb_direct(thiscol,light.brightness)
        await aio.sleep(0.05)

def start_music_result(cmd,data):
    if "error" in data:
        print("Music Mode could not {}".format(cmd))
    elif "result" in data and data["result"]==["ok"]:
        print("Music Mode was {}{}ed".format(cmd,cmd=="stop" and "p" or ""))
    else:
        print("Don't know what this response to {} is: {}".format(cmd,data))

def readin():
    """Reading from stdin and displaying menu"""

    selection = sys.stdin.readline().strip("\n")
    MyBulbs.bulbs.sort(key=lambda x: x.name or str(x.bulb_id))
    lov=[ x for x in selection.split(" ") if x != ""]
    if lov:
        if MyBulbs.boi:
            #try:
            if True:
                if int(lov[0]) == 0:
                    MyBulbs.boi=None
                elif int(lov[0]) == 1:
                    if len(lov) >1 and lov[1].lower() in ["on","off"]:
                        MyBulbs.boi.set_power(lov[1].lower())
                        MyBulbs.boi=None
                    else:
                        print("Error: For power you must indicate on or off\n")
                elif int(lov[0]) == 2:
                    if len(lov) >2:
                        try:
                            MyBulbs.boi.set_white_direct(
                                int(round(float(lov[2]))),
                                min(100,int(round(float(lov[1])))))

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
                            print("Error: For colour Hue (0-359), Saturation (0-100) and Brightness (0-100)) must be numbers.\n")
                    else:
                        print("Error: For colour you must indicate Hue (0-359), Saturation (0-100) and Brightess (0-100)\n")

                elif int(lov[0]) == 4:
                    if len(lov) >4:
                        #try:
                        MyBulbs.boi.set_hsv(min(359,int(round(float(lov[2])))),
                                            int(round(float(lov[3]))),"smooth",int(round(float(lov[1])*1000)))
                        MyBulbs.boi.set_brightness(min(100,int(round(float(lov[4])))),"smooth",int(round(float(lov[1])*1000)))
                        MyBulbs.boi=None
                        #except:
                            #print("Error: For Smooth colour Duration, Hue (0-359), Saturation (0-100) and Brightness (0-100)) must be numbers.\n")
                    else:
                        print("Error: For Smooth colour you must indicate Hue (0-359), Saturation (0-100) and Brightness (0-100)\n")
                elif int(lov[0]) == 5:
                    for prop in MyBulbs.boi.properties:
                        print("\t{}:\t{}".format(prop.title(),MyBulbs.boi.properties[prop]))
                    print("\tMessage Queue:\t{}".format(len(MyBulbs.boi.message_queue)))
                    MyBulbs.boi=None
                elif int(lov[0]) == 6:
                    try:
                        MyBulbs.boi.set_name(" ".join(lov[1:]))
                        MyBulbs.boi=None
                    except:
                        print("Error: Could not set name\n")
                elif int(lov[0]) == 7:
                    if len(lov) >3:
                        #try:
                        MyBulbs.boi.start_flow(10,"start",
                                                [100,aiox.Mode.RGB.value,int(round(float(lov[1])*65535.0+float(lov[2])*256+float(lov[3]))),
                                                    MyBulbs.boi.brightness,
                                                100,aiox.Mode.RGB.value,MyBulbs.boi.rgb,MyBulbs.boi.brightness])
                        MyBulbs.boi=None
                        #except:
                            #print("Error: For pulse Red (0-255), Green (0-255) and Blue (0-255) must be numbers.\n")
                    else:
                        print("Error: For pulse you must indicate Red (0-255), Green (0-255) and Blue (0-255)\n")
                elif int(lov[0]) == 8:
                    #try:
                    count = int(lov[1])
                    aio.ensure_future(flood_weelight(MyBulbs.boi,count))
                    MyBulbs.boi=None
                    #except:
                        #print("Error: For Stress you must specify a count (Integer)\n")
                elif int(lov[0]) == 9:
                    cmd = str(lov[1]).lower()
                    if cmd not in ["start","stop"]:
                        print("Error: For \"music mode\" you must indicate \"start\" or \"stop\"\n")
                    else:
                        MyBulbs.boi.set_music(cmd,0,partial(start_music_result,cmd))
                        MyBulbs.boi=None

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
        print("\t[1]\tPower (on or off)")
        print("\t[2]\tWhite (Brigthness Temperature)")
        print("\t[3]\tColour (Hue Saturation Brightness)")
        print("\t[4]\tSlow Colour Change (Duration Hue Saturation Brightness)")
        print("\t[5]\tInfo")
        print("\t[6]\tSet Name (Bulb name)")
        print("\t[7]\tPulse (Red Green Blue)")
        print("\t[8]\tStress (Number of colour changes)")
        print("\t[9]\tStart/Stop Music mode (start or stop)")
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



parser = argparse.ArgumentParser(description="Track and interact with Yeelight light bulbs.")
parser.add_argument("-x","--extra", action='store_true', default=False,
                    help="Print unexpected messages.")
try:
    opts = parser.parse_args()
except Exception as e:
    parser.error("Error: " + str(e))



MyBulbs= bulbs()
loop = aio.get_event_loop()
myfuture = aiox.start_xiaomi_discovery(MyBulbs.new_bulb)
myfuture.add_done_callback(lambda f: f.result().broadcast(2))
try:
    loop.add_reader(sys.stdin,readin)
    print("Hit \"Enter\" to start")
    print("Use Ctrl-C to quit")
    loop.run_forever()
except:
    pass
finally:
    print("Exiting at user's request.")
    myfuture.result().close()
    loop.remove_reader(sys.stdin)
    loop.run_until_complete(aio.sleep(2))
    loop.close()
