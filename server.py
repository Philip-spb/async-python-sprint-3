import asyncio
import json
import uuid
from datetime import datetime

from services import (MessageItem, MessagePool, ConnectionPool, ConnectionItem, InfoMsgStatuses, EOS, CHANNEL, GENERAL)

# Статистика по серверу: Отображать список созданных каналов и список подключенных имен пользователей

# Отличный пример работы с очередями
#   https://stackoverflow.com/questions/52582685/using-asyncio-queue-for-producer-consumer-flow

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

        conn = ConnectionItem(
            transport=transport,
            user_name=None
        )

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

                # TODO Отправить список всех сообщений с сервера
                #  для этого сериализовываем сообщения в список и отправляем пользователю

                # if MSG_POOL.count:
                #     self.transport.write('Channel history:\n'.encode())
                #     msgs = MSG_POOL.get_messages()
                #     for msg in msgs:
                #         message = f'[{msg.creator}] {msg.message}\n'.encode()
                #         self.transport.write(message)

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
        # FIXME отправить все сообщения из данной комнаты пользователю которые он еще не успел получить

        elif operator == InfoMsgStatuses.MESSAGE_FROM_CLIENT.value:
            # FIXME Проверить чтобы небыло больше 20 сообщений пользователя за 1 час.
            #  Иначе отказать и отправить предупреждение.

            msg = MessageItem(
                uuid=str(uuid.uuid4()),
                dt=datetime.now(),
                creator=conn.user_name,
                destination_type=CHANNEL,
                destination_name=GENERAL,
                message=args[0],
                received_users=[conn.user_name, ]
            )
            MSG_POOL.add(msg)

            CONNECTION_POOL.send_message(msg)
            return

    def connection_lost(self, exc):
        CONNECTION_POOL.del_by_transport(self.transport)
        self.send_srv_stat()


class Server:
    def __init__(self, host='127.0.0.1', port=8000, init_mes_num=20):
        self.host = host
        self.port = port
        self.init_mes_num = init_mes_num

    # async def send_data_to_clients(self):
    #     while True:
    #         now = datetime.now()
    #         answer = f'[{now}] Total connections: {CONNECTION_POOL.pool_len}'
    #         for transport in CONNECTION_POOL.get_all_transports():
    #             transport.write(f'{answer}\n'.encode())
    #         await asyncio.sleep(2)

    # async def send_data_to_clients(self):
    #     while True:
    #         data = await QUEUE.get()
    #         now = datetime.now()
    #         answer = f'[{now}] {data}'
    #         for transport in CONNECTION_POOL.get_all_transports():
    #             transport.write(f'{answer}\n'.encode())

    def listen(self):
        loop = asyncio.get_event_loop()

        srv = loop.create_server(lambda: ChatServerProtocol(self.init_mes_num), self.host, self.port)

        # loop.create_task(self.send_data_to_clients())
        loop.run_until_complete(srv)

        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    server = Server(host='127.0.0.1', port=8000, init_mes_num=20)
    server.listen()
