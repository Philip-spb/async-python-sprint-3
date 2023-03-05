from services import CHANNEL, GENERAL, PRIVATE, AVAILABLE_MSGS


def test_text_to_general_true(message_to_general_channel):
    res = message_to_general_channel.target(
        destination_type=CHANNEL,
        destination_name=GENERAL,
        user_name='BART'
    )
    assert res is True


def test_text_to_general_false(message_to_general_channel):
    res = message_to_general_channel.target(
        destination_type=CHANNEL,
        destination_name='not_general',
        user_name='BART'
    )
    assert res is False


def test_text_to_private_true(message_to_private_bart):
    res = message_to_private_bart.target(
        destination_type=PRIVATE,
        destination_name='BART',
        user_name='BART'
    )
    assert res is True


def test_text_to_private_false(message_to_private_homer):
    res = message_to_private_homer.target(
        destination_type=PRIVATE,
        destination_name='BART',
        user_name='BART'
    )
    assert res is False


def test_make_conn_banned(connection_to_springfield_not_banned):
    connection_to_springfield_not_banned.make_user_baned('Homer')
    connection_to_springfield_not_banned.make_user_baned('Marge')
    banned = connection_to_springfield_not_banned.make_user_baned('Lisa')
    assert banned is True


def test_make_conn_not_banned(connection_to_springfield_not_banned):
    connection_to_springfield_not_banned.make_user_baned('Homer')
    banned = connection_to_springfield_not_banned.make_user_baned('Lisa')
    assert banned is False


def test_conn_can_send_message(connection_to_springfield_not_banned):
    can_send, _ = connection_to_springfield_not_banned.can_send_message(is_general_channel=True)
    assert can_send is True


def test_conn_can_not_send_message(connection_to_springfield_not_banned):
    connection_to_springfield_not_banned.msgs_sent = AVAILABLE_MSGS
    can_send, _ = connection_to_springfield_not_banned.can_send_message(is_general_channel=True)
    assert can_send is False
