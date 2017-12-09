# aioxiaomi

aioxiaomi is a Python 3/asyncio library to control Xiaomi Yeelight LED lightbulbs over your LAN.

# Installation

We are on PyPi so

     pip3 install aioxiaomi
or
     python3 -m pip install aioxiaomi



# How to use

Essentially, you create an object with at least 2 methods:

    - register
    - unregister

You then start the XiaomiDiscovery task in asyncio with a callback that will create and .activate() any new bulb.
Upon connection with the bulb, it will register itself with the parent. All the method communicating with the bulb
can be passed a callback function to react to the bulb response. The callback should take 2 parameters:

    - a light object
    - the response message

Checkout __main__.py to see how it works.


In essence, the test program is this

    class bulbs():
    """ A simple class with a register and  unregister methods
    """
        def __init__(self):
            self.bulbs=[]
            self.pending_bulbs = []

        def register(self,bulb):
            self.bulbs.append(bulb)
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
            newbulb = aiox.XiaomiBulb(aio.get_event_loop(),kwargs['headers'],self)
            found = False
            for x in self.bulbs:
                if x.bulb_id == newbulb.bulb_id:
                    found = True
                    break
            if not found:
                for x in self.pending_bulbs:
                    if x.bulb_id == newbulb.bulb_id:
                        found = True
                        break
            if not found:
                newbulb.activate()
            else:
                del(newbulb)


    def readin():
    """Reading from stdin and displaying menu"""

        selection = sys.stdin.readline().strip("\n")
        DoSomething()

    MyBulbs= bulbs()
    loop = aio.get_event_loop()
    coro = aiox.start_xiaomi_discovery(MyBulbs.new_bulb)
    transp, server = loop.run_until_complete(coro)
    try:
        loop.add_reader(sys.stdin,readin)
        server.broadcast(2)
        loop.run_forever()
    except:
        pass
    finally:
        server.cancel()
        loop.remove_reader(sys.stdin)
        loop.close()


Other things worth noting:

    - Whilst XiaomiDiscover uses UDP broadcast, the bulbs are
      connected with Unicast TCP

    - Xiaomi allows only about 1 command per second per connection. To counter that,
      one can start more than one connection to a bulb. There is a limit of
      4 connections per bulb, but given that there can only be 144 command per minute
      per bulb, only 2 connections can be handled without starting to overload the bulb.
      Use .set_connection(x) before activate to set the number of connections

    - aioxiaomi ensure that there is at most 1 command per second per connection. To do so
      it keeps a buffer of messages and pace the sending (using round-robin if there is more
      then one connection). The buffer can thus become quite big. To control this, one can
      specify a maximum buffer length and what to do with messages that comes when the buffer
      is full. Use set_queue_limit(length,policy) to control.
                length is the maximum number of commands waiting to be sent
                policy defines what to do with the extra packets:
                    drop: just drop them
                    head: queue them but discard the head of the queue
                    random: queue the message then discard a random element of the queue
                    adapt: switch to the so-called "music mode" and dump all the messages.
                           After 5 secs inactivity, the "music mode" is cancelled

    - The socket connecting to a bulb is not closed unless the bulb is deemed to have
      gone the way of the Dodo.

    - I only have "Color" model, so I could not test with other types
      of bulbs
