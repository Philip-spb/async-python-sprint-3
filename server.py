import asyncio
import json
import logging
import uuid
from datetime import datetime

from services import (MessageItem, MessagePool, ConnectionPool, ConnectionItem, InfoMsgStatuses,
                      EOS, CHANNEL, PRIVATE, INIT_MSGS_CNT, BLOCK_INTERVAL, GENERAL)

logger = logging.getLogger()

QUEUE = asyncio.Queue()

MSG_POOL = MessagePool()
CONNECTION_POOL = ConnectionPool()


class ChatServerProtocol(asyncio.Protocol):

    @staticmethod
    def make_statistic_str() -> str:
        usr_names_lst = CONNECTION_POOL.get_all_user_names()
        channels_names_lst = CONNECTION_POOL.get_all_channel_names()

        srv_stat = dict()
        srv_stat['users'] = usr_names_lst
        srv_stat['channels'] = channels_names_lst

        srv_stat_str = json.dumps(srv_stat, ensure_ascii=False)
        message = f'{InfoMsgStatuses.SET_STATISTIC.value} {srv_stat_str}'

        return message

    def send_srv_stat(self, except_trs=None):
        message = self.make_statistic_str()
        for transport in CONNECTION_POOL.get_all_transports():
            if not except_trs or transport != except_trs:
                transport.write(message.encode())

    def connection_made(self, transport):

        transport.write(InfoMsgStatuses.CHOOSE_NAME.msg_bts)
        self.transport = transport
        conn = ConnectionItem(transport=transport, user_name=None)
        CONNECTION_POOL.add(conn)

    def data_received(self, data):  # noqa C901

        conn = CONNECTION_POOL.get_by_transport(self.transport)
        text = data.decode().strip()

        if not conn.user_name:
            if text in CONNECTION_POOL.get_all_user_names():
                self.transport.write(InfoMsgStatuses.NAME_REJECTED.msg_bts + EOS)
                return
            else:
                conn.user_name = text
                self.transport.write(InfoMsgStatuses.NAME_ACCEPTED.msg_bts + b' ' + data + EOS)

                # At the first connection sending all messages to the user
                if MSG_POOL.count:
                    msgs = MSG_POOL.get_messages()

                    msg_to_client = msgs
                    msgs_len = len(msgs)
                    if msgs_len > INIT_MSGS_CNT:

                        # Send to the client only `INIT_MSGS_CNT` last messages
                        msg_to_client = msgs[msgs_len - INIT_MSGS_CNT:]
                        lost_messages = msgs[:msgs_len - INIT_MSGS_CNT]
                        for msg in lost_messages:
                            msg.received_users.append(conn.user_name)

                    for msg in msg_to_client:
                        QUEUE.put_nowait((msg, self.transport))
                return

        operator, *args = data.decode().strip().split(' ', 1)

        if operator == InfoMsgStatuses.GET_STATISTIC.value:
            message = self.make_statistic_str().encode()
            self.transport.write(message)
            return

        elif operator == InfoMsgStatuses.MESSAGE_APPROVE.value:
            msg = json.loads(args[0])
            id = msg['uuid']
            user = msg['user']
            message = MSG_POOL.get_message_by_uuid(id)
            if message:
                message.received_users.append(user)
            return

        elif operator == InfoMsgStatuses.CHANGE_CHAT.value:
            chat_type, chat_name = args[0].strip().split(' ', 1)
            conn = CONNECTION_POOL.get_by_transport(self.transport)
            if conn:
                conn.current_connection_type = chat_type
                conn.current_connection_name = chat_name
                self.transport.write(data)

                if chat_type == CHANNEL:
                    msgs = MSG_POOL.get_messages(
                        destination_type=CHANNEL,
                        destination_name=chat_name,
                        not_received_user=conn.user_name,
                        not_from_creator=conn.user_name
                    )

                else:  # elif chat_type == PRIVATE:
                    msgs = MSG_POOL.get_messages(
                        destination_type=PRIVATE,
                        destination_name=conn.user_name,
                        not_received_user=conn.user_name,
                        creator=chat_name,
                        not_from_creator=conn.user_name
                    )

                for msg in msgs:
                    QUEUE.put_nowait((msg, self.transport))

        elif operator == InfoMsgStatuses.BAN_USER.value:
            who_send_ban = conn.user_name
            banned_user = args[0]
            ban_conn = CONNECTION_POOL.get_by_user_name(banned_user)
            if ban_conn:
                if ban_conn.make_user_baned(who_send_ban):
                    ban_msg = f'You has been baned until `{ban_conn.ban_time.ctime()}` '
                    ban_msg += 'and you can\'t send messages'
                    ban_conn.transport.write(ban_msg.encode())
            else:
                logger.error(f'Can\'t find connection for user {banned_user}')

        elif operator == InfoMsgStatuses.MESSAGE_FROM_CLIENT.value:

            sending_to_general_channel = False
            if conn.current_connection_type == CHANNEL and conn.current_connection_name == GENERAL:
                sending_to_general_channel = True

            can_send, error_text = conn.can_send_message(sending_to_general_channel)
            if not can_send:
                self.transport.write(error_text.encode())
                return

            if sending_to_general_channel:
                conn.increment_msgs_sent()

            try:
                msg_text = args[0]
            except IndexError:
                logger.info('Can\'t read the message text')
                return

            msg = MessageItem(uuid=str(uuid.uuid4()), dt=datetime.now(), creator=conn.user_name,
                              destination_type=conn.current_connection_type,
                              destination_name=conn.current_connection_name,
                              message=msg_text, received_users=[]
                              )

            MSG_POOL.add(msg)

            CONNECTION_POOL.send_message(msg)
            return

    def connection_lost(self, exc):
        CONNECTION_POOL.del_by_transport(self.transport)


class Server:
    def __init__(self, host, port):
        self.host = host
        self.port = port

    async def send_messages_from_queue(self):

        while True:
            msg_item, transport = await QUEUE.get()
            await asyncio.sleep(0.001)
            message = f'{InfoMsgStatuses.MESSAGE_FROM_SRV.value} {msg_item.serialize()}\n'.encode()
            transport.write(message)

    async def clear_interval_limits(self):
        """
        Clearing the history of count messages sent to the general channel
        """

        while True:
            await asyncio.sleep(BLOCK_INTERVAL * 60)
            CONNECTION_POOL.clear_all_msgs_sent()
            logger.info('Cleared the history of messages sent at the general channel')

    async def deleting_delivered_messages(self):

        while True:
            del_msgs_count = MSG_POOL.delete_delivered_messages()
            if del_msgs_count:
                logger.info(f'Has been deleted delivered messages ({del_msgs_count})')
            await asyncio.sleep(0.001)

    def listen(self):
        loop = asyncio.get_event_loop()

        srv = loop.create_server(lambda: ChatServerProtocol(), self.host, self.port)

        loop.create_task(self.send_messages_from_queue())
        loop.create_task(self.clear_interval_limits())
        loop.create_task(self.deleting_delivered_messages())
        loop.run_until_complete(srv)

        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':

    print('Choose server host (by default 127.0.0.1)')
    server_host = input()
    print('Choose server port (by default 8000)')
    server_port = input()

    if not server_host:
        server_host = '127.0.0.1'

    if not server_port:
        server_port = 8000
    else:
        server_port = int(server_port)

    server = Server(host=server_host, port=server_port)

    print(f'Server started at host {server_host}:{server_port}')

    server.listen()
