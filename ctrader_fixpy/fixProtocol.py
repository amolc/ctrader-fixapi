#!/usr/bin/env python
"""Optimized FIX Protocol with better bundled message handling."""

from twisted.internet.protocol import Protocol
from .messages import ResponseMessage


class FixProtocol(Protocol):
    """Optimized FIX protocol handler."""
    _currentMessage = ''

    def connectionMade(self):
        self.factory.messageSequenceNumber = 0
        super().connectionMade()
        self.factory.connected()

    def connectionLost(self, reason):
        super().connectionLost()
        self.factory.disconnected(reason)

    def dataReceived(self, data):
        """Optimized data reception with better bundled message detection."""
        dataString = data.decode("ascii")
        self._currentMessage += dataString

        # Check for complete FIX message(s) - look for checksum field (10=XXX)
        delimiter = self.factory.delimiter

        while True:
            # Find checksum field
            checksum_idx = self._currentMessage.find(f"{delimiter}10=")
            if checksum_idx == -1:
                break  # No complete message yet

            # Find end of checksum (3 digits + delimiter)
            checksum_start = checksum_idx + len(f"{delimiter}10=")
            checksum_end = self._currentMessage.find(delimiter, checksum_start)

            if checksum_end == -1:
                # Checksum value incomplete
                if len(self._currentMessage) - checksum_start < 3:
                    break
                checksum_end = checksum_start + 3

            # Extract complete message
            message_end = checksum_end + len(delimiter)
            complete_message = self._currentMessage[:message_end]
            self._currentMessage = self._currentMessage[message_end:]

            # Process the complete message
            responseMessage = ResponseMessage(complete_message, delimiter)
            self.factory.received(responseMessage)

    def send(self, requestMessage):
        """Send a FIX message."""
        self.factory.messageSequenceNumber += 1
        messageString = requestMessage.getMessage(self.factory.messageSequenceNumber)
        return self.transport.write(messageString.encode("ascii"))
