import logging
import asyncio as aio
import socket
from struct import pack
from functools import partial

log = logging.getLogger(__name__)

UPNP_PORT = 1982
UPNP_ADDR = "239.255.255.250"
_DISCOVERYTIMEOUT = 360

class UPnPLoopbackException(Exception):
    """
    Using loopback interface as callback IP.
    """

class XiaomiUPnP(aio.Protocol):
    """Class used to monitor UPnP messages from Yeelight bulbs.
    """
    def __init__(self, loop,addr,handler,future):
        super().__init__()
        self.loop = loop
        self.transport = None
        self.addr=addr
        self.handler = handler
        self.task = None
        self.clients = {}
        self.broadcast_cnt=0
        self.future=future
        self.discovery_timeout = _DISCOVERYTIMEOUT

    def connection_made(self, transport):
        self.transport = transport
        self.future.set_result(self)
        sock = self.transport.get_extra_info('socket')
        sock.settimeout(3)
        addrinfo = socket.getaddrinfo(self.addr, None)[0]
        ttl = pack('@i', 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

    def broadcast_once(self):
        """Send the discovery mesage broadcast_once
        """
        request = '\r\n'.join(("M-SEARCH * HTTP/1.1",
                               "HOST:{}:{}",
                               "ST:wifi_bulb",
                               "MX:2",
                               'MAN:"ssdp:discover"',
                               "", "")).format(self.addr,UPNP_PORT)
        self.transport.sendto(request.encode(), (self.addr,UPNP_PORT))


    def datagram_received(self, data, addr):
        #print("Received datagram: {}".format(data))
        headers = {}
        for line in data.decode("ascii").split("\r\n"):
            try:
                header, value = line.split(":", 1)
                headers[header.lower()] = value.strip()
            except:
                pass

        if self.handler:
            self.handler(addr,headers)


    def error_received(self, name):
        pass
        #print('Error received:', exc)

    def connection_lost(self, udn):
        udn = udn.split(":")[1]
        del self.clients[udn]
        pass

    def broadcast(self,seconds,timeout=_DISCOVERYTIMEOUT):
        self.discovery_timeout = timeout
        self.task= aio.get_event_loop().create_task(self._do_broadcast(seconds))

    async def _do_broadcast(self,seconds):
        count = seconds
        while True:
            if count == 0:
                count = seconds
                await aio.sleep(self.discovery_timeout)
            self.broadcast_once()
            count -= 1
            await aio.sleep(1)

    def close(self):
        try:
            self.task.cancel()
        except:
            pass


def start_xiaomi_discovery(handler):
    addrinfo = socket.getaddrinfo(UPNP_ADDR, None)[0]
    sock = socket.socket(addrinfo[0], socket.SOCK_DGRAM)
    loop = aio.get_event_loop()
    future = aio.Future()
    connect = loop.create_datagram_endpoint(
        lambda: XiaomiUPnP(loop,UPNP_ADDR,handler,future),
        sock=sock
    )
    x=aio.ensure_future(connect)
    return future

def test():
    logging.basicConfig(level=logging.DEBUG)
    broadcaster = {}
    def handler(sender, **kwargs):
        print("I GOT ONE")
        print(kwargs['address'], kwargs['headers'])


    loop = aio.get_event_loop()
    connect = start_xiaomi_discovery(handler)
    broadcaster[UPNP_ADDR] = loop.run_until_complete(connect)
    broadcaster[UPNP_ADDR][1].broadcast(2)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("\n", "Exiting at user's request")
    finally:
        # Close the server
        for transport, protocol in broadcaster.values():
            try:
                if protocol.task:
                    protocol.task.cancel()
            except:
                pass
            transport.close()
        loop.close()


if __name__ == "__main__":
    test()
