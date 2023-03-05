from asyncio import BaseTransport
from datetime import datetime

import pytest

from services import MessageItem, CHANNEL, GENERAL, PRIVATE, ConnectionItem


@pytest.fixture
def message_to_general_channel() -> MessageItem:
    msg = MessageItem(
        uuid='123',
        dt=datetime(year=2023, month=1, day=1, hour=0, minute=0, second=1),
        creator='Name1',
        destination_type=CHANNEL,
        destination_name=GENERAL,
        message='text1',
        received_users=[]
    )
    return msg


@pytest.fixture
def message_to_private_bart() -> MessageItem:
    msg = MessageItem(
        uuid='124',
        dt=datetime(year=2023, month=1, day=1, hour=0, minute=0, second=2),
        creator='Name1',
        destination_type=PRIVATE,
        destination_name='BART',
        message='text2',
        received_users=[]
    )
    return msg


@pytest.fixture
def message_to_private_homer() -> MessageItem:
    msg = MessageItem(
        uuid='124',
        dt=datetime(year=2023, month=1, day=1, hour=0, minute=0, second=2),
        creator='Name1',
        destination_type=PRIVATE,
        destination_name='HOMER',
        message='text2',
        received_users=[]
    )
    return msg


@pytest.fixture
def connection_to_springfield_not_banned() -> ConnectionItem:
    conn = ConnectionItem(
        transport=BaseTransport(),
        user_name='Bart',
    )
    return conn
