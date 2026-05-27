#!/usr/bin/env python
"""Optimized FIX Client with better callback handling."""

from twisted.internet.endpoints import HostnameEndpoint, wrapClientTLS
from twisted.internet.ssl import optionsForClientTLS
from twisted.application.internet import ClientService
from twisted.internet import reactor
from .messages import ResponseMessage
from .factory import Factory
from .fixProtocol import FixProtocol


class Client(ClientService):
    """Optimized FIX client with improved message handling."""

    def __init__(self, host, port, ssl=False, delimiter="\x01", retryPolicy=None, clock=None, prepareConnection=None):
        self._runningReactor = reactor
        self.delimiter = delimiter

        # Create endpoint with or without SSL
        if ssl:
            # Use TLS with default options
            tls_options = optionsForClientTLS(hostname=host)
            endpoint = wrapClientTLS(tls_options, HostnameEndpoint(self._runningReactor, host, port))
        else:
            # Plain TCP
            endpoint = HostnameEndpoint(self._runningReactor, host, port)
        self._factory = Factory.forProtocol(FixProtocol, client=self)
        super().__init__(
            endpoint,
            self._factory,
            retryPolicy=retryPolicy,
            clock=clock,
            prepareConnection=prepareConnection
        )
        self._events = {}
        self._responseDeferreds = {}
        self.isConnected = False
        self._connectedCallback = None
        self._disconnectedCallback = None
        self._messageReceivedCallback = None

    def startService(self):
        if self.running:
            return
        ClientService.startService(self)

    def stopService(self):
        if self.running and self.isConnected:
            ClientService.stopService(self)

    def _connected(self):
        self.isConnected = True
        if self._connectedCallback:
            self._connectedCallback(self)

    def _disconnected(self, reason):
        self.isConnected = False
        self._responseDeferreds.clear()
        if self._disconnectedCallback:
            self._disconnectedCallback(self, reason)

    def _received(self, responseMessage):
        """Process received message through callback."""
        if self._messageReceivedCallback:
            self._messageReceivedCallback(self, responseMessage)

    def send(self, requestMessage):
        """Send a request message."""
        requestMessage.delimiter = self.delimiter
        deferred = self.whenConnected(failAfterFailures=1)
        deferred.addCallback(lambda protocol: protocol.send(requestMessage))
        return deferred

    def changeMessageSequenceNumber(self, newMessageSequenceNumber):
        self._factory.messageSequenceNumber = newMessageSequenceNumber

    def getMessageSequenceNumber(self):
        return self._factory.messageSequenceNumber

    def setConnectedCallback(self, callback):
        self._connectedCallback = callback

    def setDisconnectedCallback(self, callback):
        self._disconnectedCallback = callback

    def setMessageReceivedCallback(self, callback):
        self._messageReceivedCallback = callback
