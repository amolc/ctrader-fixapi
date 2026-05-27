#!/usr/bin/env python
"""Optimized FIX Messages with better bundled message support."""

import datetime


class ResponseMessage:
    """Optimized response message parser with direct field access."""

    def __init__(self, message, delimiter):
        self._message = message.replace(delimiter, "|")
        self._delimiter = delimiter
        self._fields = {}  # dict: field_number -> list of values
        self._raw_fields = []  # list of (field_number, value)

        # Parse fields
        for field in message.split(delimiter):
            if field != "" and "=" in field:
                parts = field.split("=", 1)
                field_num = int(parts[0])
                value = parts[1]
                self._raw_fields.append((field_num, value))
                if field_num not in self._fields:
                    self._fields[field_num] = []
                self._fields[field_num].append(value)

    def getFieldValue(self, fieldNumber):
        """Get field value(s). Returns single value or list for bundled messages."""
        values = self._fields.get(fieldNumber, [])
        if len(values) == 0:
            return None
        elif len(values) == 1:
            return values[0]
        return values

    def getFieldValues(self, fieldNumber):
        """Always return a list of values (even single value wrapped in list)."""
        values = self._fields.get(fieldNumber, [])
        return values if values else []

    def getMessageType(self):
        """Get the message type (tag 35)."""
        return self.getFieldValue(35)

    def getMessageTypes(self):
        """Get all message types (for bundled messages)."""
        return self.getFieldValues(35)

    def getMessage(self):
        return self._message

    def isBundled(self):
        """Check if this is a bundled message with multiple messages."""
        types = self._fields.get(35, [])
        return len(types) > 1


class RequestMessage:
    """Base class for FIX request messages."""
    delimiter = "\x01"

    def __init__(self, messageType, config):
        self._type = messageType
        self._config = config

    def getMessage(self, sequenceNumber):
        body = self._getBody()
        if body is not None:
            header = self._getHeader(len(body), sequenceNumber)
            headerAndBody = f"{header}{self.delimiter}{body}{self.delimiter}"
        else:
            header = self._getHeader(0, sequenceNumber)
            headerAndBody = f"{header}{self.delimiter}"
        trailer = self._getTrailer(headerAndBody)
        return f"{headerAndBody}{trailer}{self.delimiter}"

    def _getBody(self):
        return None

    def _getHeader(self, lenBody, sequenceNumber):
        fields = []
        fields.append(f"35={self._type}")
        fields.append(f"49={self._config['SenderCompID']}")
        fields.append(f"56={self._config['TargetCompID']}")
        fields.append(f"57={self._config['TargetSubID']}")
        fields.append(f"50={self._config['SenderSubID']}")
        fields.append(f"34={sequenceNumber}")
        fields.append(f"52={datetime.datetime.utcnow().strftime('%Y%m%d-%H:%M:%S')}")
        fieldsJoined = self.delimiter.join(fields)
        return f"8={self._config['BeginString']}{self.delimiter}9={lenBody+len(fieldsJoined) + 2}{self.delimiter}{fieldsJoined}"

    def _getTrailer(self, headerAndBody):
        messageBytes = bytes(headerAndBody, "ascii")
        checksum = 0
        for byte in messageBytes:
            checksum += byte
        checksum = checksum % 256
        return f"10={str(checksum).zfill(3)}"


class LogonRequest(RequestMessage):
    def __init__(self, config):
        super().__init__("A", config)
        self.EncryptionScheme = 0

    def _getBody(self):
        fields = []
        fields.append(f"98={self.EncryptionScheme}")
        fields.append(f"108={self._config['HeartBeat']}")
        if hasattr(self, "ResetSeqNum") and self.ResetSeqNum:
            fields.append(f"141=Y")
        fields.append(f"553={self._config['Username']}")
        fields.append(f"554={self._config['Password']}")
        return f"{self.delimiter.join(fields)}"


class Heartbeat(RequestMessage):
    def __init__(self, config):
        super().__init__("0", config)

    def _getBody(self):
        if hasattr(self, "TestReqID"):
            return f"112={self.TestReqID}"
        return None


class TestRequest(RequestMessage):
    def __init__(self, config):
        super().__init__("1", config)

    def _getBody(self):
        return f"112={self.TestReqID}"


class LogoutRequest(RequestMessage):
    def __init__(self, config):
        super().__init__("5", config)


class ResendRequest(RequestMessage):
    def __init__(self, config):
        super().__init__("2", config)

    def _getBody(self):
        fields = []
        fields.append(f"7={self.BeginSeqNo}")
        fields.append(f"16={self.EndSeqNo}")
        return f"{self.delimiter.join(fields)}"


class SequenceReset(RequestMessage):
    def __init__(self, config):
        super().__init__("4", config)

    def _getBody(self):
        fields = []
        if hasattr(self, "GapFillFlag"):
            fields.append(f"123={self.GapFillFlag}")
        fields.append(f"36={self.NewSeqNo}")
        return f"{self.delimiter.join(fields)}"


class MarketDataRequest(RequestMessage):
    def __init__(self, config):
        super().__init__("V", config)

    def _getBody(self):
        fields = []
        fields.append(f"262={self.MDReqID}")
        fields.append(f"263={self.SubscriptionRequestType}")
        fields.append(f"264={self.MarketDepth}")
        if hasattr(self, "MDUpdateType"):
            fields.append(f"265={self.MDUpdateType}")
        fields.append(f"267={self.NoMDEntryTypes}")
        fields.append(f"269={self.MDEntryType}")
        fields.append(f"146={self.NoRelatedSym}")
        fields.append(f"55={self.Symbol}")
        return f"{self.delimiter.join(fields)}"


class NewOrderSingle(RequestMessage):
    def __init__(self, config):
        super().__init__("D", config)

    def _getBody(self):
        fields = []
        fields.append(f"11={self.ClOrdID}")
        fields.append(f"55={self.Symbol}")
        fields.append(f"54={self.Side}")
        # TransactTime format: YYYYMMDD-HH:MM:SS
        if hasattr(self, "TransactTime"):
            fields.append(f"60={self.TransactTime.strftime('%Y%m%d-%H:%M:%S')}")
        else:
            fields.append(f"60={datetime.datetime.utcnow().strftime('%Y%m%d-%H:%M:%S')}")
        fields.append(f"38={self.OrderQty}")
        fields.append(f"40={self.OrdType}")
        # Optional fields
        if hasattr(self, "Price"):
            fields.append(f"44={self.Price}")
        if hasattr(self, "StopPx"):
            fields.append(f"99={self.StopPx}")
        if hasattr(self, "ExpireTime"):
            fields.append(f"126={self.ExpireTime.strftime('%Y%m%d-%H:%M:%S')}" if isinstance(self.ExpireTime, datetime.datetime) else f"126={self.ExpireTime}")
        if hasattr(self, "PosMaintRptID"):
            fields.append(f"721={self.PosMaintRptID}")
        if hasattr(self, "Designation"):
            fields.append(f"494={self.Designation}")
        return f"{self.delimiter.join(fields)}"


class OrderStatusRequest(RequestMessage):
    def __init__(self, config):
        super().__init__("H", config)

    def _getBody(self):
        fields = []
        fields.append(f"11={self.ClOrdID}")
        if hasattr(self, "Side"):
            fields.append(f"54={self.Side}")
        return f"{self.delimiter.join(fields)}"


class OrderMassStatusRequest(RequestMessage):
    def __init__(self, config):
        super().__init__("AF", config)

    def _getBody(self):
        fields = []
        fields.append(f"584={self.MassStatusReqID}")
        fields.append(f"585={self.MassStatusReqType}")
        if hasattr(self, "IssueDate"):
            fields.append(f"225={self.IssueDate.strftime('%Y%m%d-%H:%M:%S')}")
        return f"{self.delimiter.join(fields)}"


class RequestForPositions(RequestMessage):
    def __init__(self, config):
        super().__init__("AN", config)

    def _getBody(self):
        fields = []
        fields.append(f"710={self.PosReqID}")
        if hasattr(self, "PosMaintRptID"):
            fields.append(f"721={self.PosMaintRptID}")
        return f"{self.delimiter.join(fields)}"


class OrderCancelRequest(RequestMessage):
    def __init__(self, config):
        super().__init__("F", config)

    def _getBody(self):
        fields = []
        fields.append(f"41={self.OrigClOrdID}")
        if hasattr(self, "OrderID"):
            fields.append(f"37={self.OrderID}")
        fields.append(f"11={self.ClOrdID}")
        return f"{self.delimiter.join(fields)}"


class OrderCancelReplaceRequest(RequestMessage):
    def __init__(self, config):
        super().__init__("G", config)

    def _getBody(self):
        fields = []
        fields.append(f"41={self.OrigClOrdID}")
        if hasattr(self, "OrderID"):
            fields.append(f"37={self.OrderID}")
        fields.append(f"11={self.ClOrdID}")
        fields.append(f"38={self.OrderQty}")
        if hasattr(self, "Price"):
            fields.append(f"44={self.Price}")
        if hasattr(self, "StopPx"):
            fields.append(f"99={self.StopPx}")
        if hasattr(self, "ExpireTime"):
            fields.append(f"126={self.ExpireTime.strftime('%Y%m%d-%H:%M:%S')}")
        return f"{self.delimiter.join(fields)}"


class SecurityListRequest(RequestMessage):
    def __init__(self, config):
        super().__init__("x", config)

    def _getBody(self):
        fields = []
        fields.append(f"320={self.SecurityReqID}")
        fields.append(f"559={self.SecurityListRequestType}")
        if hasattr(self, "Symbol"):
            fields.append(f"55={self.Symbol}")
        return f"{self.delimiter.join(fields)}"


class TradeCaptureReportRequest(RequestMessage):
    """Request trade history (closed trades/executions)."""
    def __init__(self, config):
        super().__init__("AD", config)

    def _getBody(self):
        fields = []
        fields.append(f"568={self.TradeRequestID}")
        fields.append(f"569={self.TradeRequestType}")  # 0=All, 1=Matched, 2=Unmatched
        fields.append(f"263={self.SubscriptionRequestType}")  # 0=Snapshot, 1=Subscribe, 2=Unsubscribe
        return f"{self.delimiter.join(fields)}"
