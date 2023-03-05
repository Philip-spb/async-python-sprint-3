import asyncio
import json
import uuid
from datetime import datetime

from services import (MessageItem, MessagePool, ConnectionPool, ConnectionItem, InfoMsgStatuses, EOS, CHANNEL, PRIVATE)

# Статистика по серверу: Отображать список созданных каналов и список подключенных имен пользователей

# Отличный пример работы с очередями
#   https://stackoverflow.com/questions/52582685/using-asyncio-queue-for-producer-consumer-flow

QUEUE = asyncio.Queue()

MSG_POOL = MessagePool()
CONNECTION_POOL = ConnectionPool()


class ChatServerProtocol(asyncio.Protocol):

    def __init__(self, init_mes_num):
        self.init_mes_num = init_mes_num

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

    def data_received(self, data):

        conn = CONNECTION_POOL.get_by_transport(self.transport)
        text = data.decode().strip()

        if not conn.user_name:
            if text in CONNECTION_POOL.get_all_user_names():
                self.transport.write(InfoMsgStatuses.NAME_REJECTED.msg_bts + EOS)
                return
            else:
                conn.user_name = text
                self.transport.write(InfoMsgStatuses.NAME_ACCEPTED.msg_bts + b' ' + data + EOS)
                self.send_srv_stat(except_trs=self.transport)

                # At the first connection sending all messages to the user
                if MSG_POOL.count:
                    msgs = MSG_POOL.get_messages()

                    msg_to_client = msgs
                    msgs_len = len(msgs)
                    if msgs_len > self.init_mes_num:

                        # Send to the client only `init_mes_num` last messages
                        msg_to_client = msgs[msgs_len - self.init_mes_num:]
                        lost_messages = msgs[:msgs_len - self.init_mes_num]
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

                elif chat_type == PRIVATE:
                    msgs = MSG_POOL.get_messages(
                        destination_type=PRIVATE,
                        destination_name=conn.user_name,
                        not_received_user=conn.user_name,
                        creator=chat_name,
                        not_from_creator=conn.user_name
                    )

                for msg in msgs:
                    QUEUE.put_nowait((msg, self.transport))

        elif operator == InfoMsgStatuses.MESSAGE_FROM_CLIENT.value:
            # FIXME Проверить чтобы небыло больше 20 сообщений пользователя за 1 час.
            #  Иначе отказать и отправить предупреждение.

            try:
                msg_text = args[0]
            except IndexError:
                # TODO log
                return

            msg = MessageItem(
                uuid=str(uuid.uuid4()),
                dt=datetime.now(),
                creator=conn.user_name,
                destination_type=conn.current_connection_type,
                destination_name=conn.current_connection_name,
                message=msg_text,
                received_users=[]
            )
            MSG_POOL.add(msg)

            CONNECTION_POOL.send_message(msg)
            return

    def connection_lost(self, exc):
        CONNECTION_POOL.del_by_transport(self.transport)
        self.send_srv_stat()


class Server:
    def __init__(self, host, port, init_mes_num):
        self.host = host
        self.port = port
        self.init_mes_num = init_mes_num

    async def send_messages_from_queue(self):

        while True:
            msg_item, transport = await QUEUE.get()
            message = f'{InfoMsgStatuses.MESSAGE_FROM_SRV.value} {msg_item.serialize()}\n'.encode()
            transport.write(message)
            await asyncio.sleep(0.001)

    def listen(self):
        loop = asyncio.get_event_loop()

        srv = loop.create_server(lambda: ChatServerProtocol(self.init_mes_num), self.host, self.port)

        loop.create_task(self.send_messages_from_queue())
        loop.run_until_complete(srv)

        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    server = Server(host='127.0.0.1', port=8000, init_mes_num=3)
    server.listen()
