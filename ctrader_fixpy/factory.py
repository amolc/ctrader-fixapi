#!/usr/bin/env python
"""Optimized FIX Client Factory."""

from twisted.internet.protocol import ClientFactory


class Factory(ClientFactory):
    """Optimized factory with sequence number tracking."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.client = kwargs['client']
        self.delimiter = self.client.delimiter
        self.messageSequenceNumber = 0

    def connected(self):
        self.client._connected()

    def disconnected(self, reason):
        self.client._disconnected(reason)

    def received(self, message):
        self.client._received(message)
