import asyncio
import json
import logging
import signal
from typing import List, Tuple

from services import InfoMsgStatuses, CHANNEL, GENERAL, PRIVATE

logger = logging.getLogger()


class GracefulExit(SystemExit):
    code = 1


def raise_graceful_exit():
    raise GracefulExit()


class ChatClientProtocol(asyncio.Protocol):
    def __init__(self, on_con_lost, on_name_chosen):
        self.on_con_lost = on_con_lost
        self.on_name_chosen = on_name_chosen
        self.own_name = None
        self.transport = None

        # At the start, we connect a user to the default channel
        self.current_connection_type = CHANNEL
        self.current_connection_name = GENERAL

    def get_statistics(self, stat: dict) -> List[Tuple]:
        stat = [
            ('Your own name', self.own_name,),
            ('All users count', len(stat['users'])),
            ('List of all users', ', '.join(stat['users'])),
            ('List of all channels', ', '.join(stat['channels']))
        ]
        return stat

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):  # noqa C901
        operator, *args = data.decode().strip().split(' ', 1)

        if operator == InfoMsgStatuses.CHOOSE_NAME.value:
            print('Choose username')

        elif operator == InfoMsgStatuses.NAME_REJECTED.value:
            print('This username is already in use\nPlease choose another one')

        elif operator == InfoMsgStatuses.NAME_ACCEPTED.value:
            self.own_name = args[0]
            print(f'OK! Your name is {self.own_name}')
            print('To show statistics, write `get_statistic`')
            print('To ban a user, write `ban_user USER_NAME`')
            print('-' * 30)
            self.on_name_chosen.set_result(True)

        elif operator == InfoMsgStatuses.CHANGE_CHAT.value:
            chat_type, chat_name = args[0].strip().split(' ', 1)
            self.current_connection_type = chat_type
            self.current_connection_name = chat_name
            print(f'Current chat type: {self.current_connection_type}, '
                  f'and connection name: {self.current_connection_name}')

        elif operator == InfoMsgStatuses.SET_STATISTIC.value:

            print('-' * 30)
            for text, value in self.get_statistics(json.loads(args[0])):
                print(f'{text}: {value}')
            print('To change to a private channel, write `change_chat private USER_NAME`')
            print('To change to a channel, write `change_chat channel general`')
            print('-' * 30)

        elif operator == InfoMsgStatuses.MESSAGE_FROM_SRV.value:

            try:
                msg_text = args[0]
            except IndexError:
                logger.error(f'Can\'t read message {data.decode()}')
                return

            msg = json.loads(msg_text)
            uuid = msg['uuid']
            creator = msg['creator']
            destination_type = msg['destination_type']
            destination_name = msg['destination_name']

            # If a user situating at the correct channel - printing and sending a signal
            #   about the message has been read

            if ((
                    destination_type == CHANNEL
                    and self.current_connection_type == destination_type
                    and self.current_connection_name == destination_name
            ) or (
                    destination_type == PRIVATE
                    and self.current_connection_type == destination_type
                    and self.own_name == destination_name
                    and self.current_connection_name == creator
            )):
                message = msg['message']
                print(f'[{creator}] {message}')

                msg_to_srv = {
                    'uuid': uuid,
                    'user': self.own_name
                }

                command = InfoMsgStatuses.MESSAGE_APPROVE.value
                msg_to_srv = json.dumps(msg_to_srv)

                approval_to_srv = f'{command} {msg_to_srv}'.encode()
                self.transport.write(approval_to_srv)

        else:
            print(data.decode())

    def connection_lost(self, exc):
        print('The server closed the connection')
        self.on_con_lost.set_result(True)


class Client:
    def __init__(self, server_host='127.0.0.1', server_port=8000):
        self.server_host = server_host
        self.server_port = server_port
        self.transport = None
        self.name_chosen = False

    def send(self, message: str = ''):
        self.transport.write(message.encode())

    def input_func(self):
        """
        Функция для ввода текста в консоли
        """
        while True:
            try:
                message = input()
            except EOFError:
                break

            command, *args = message.strip().split(' ', 1)

            if not self.name_chosen:
                self.send(message)

            elif command == InfoMsgStatuses.CHANGE_CHAT.value:
                # Сменяем чат комнату
                try:
                    chat_type, chat_name = args[0].strip().split(' ', 1)
                    assert chat_type in [CHANNEL, PRIVATE]
                    self.send(message)
                except (ValueError, AssertionError):
                    print('Wrong chat type')

            elif command == InfoMsgStatuses.GET_STATISTIC.value:
                self.send(InfoMsgStatuses.GET_STATISTIC.value)

            elif command == InfoMsgStatuses.BAN_USER.value:
                self.send(message)

            else:
                message = f'{InfoMsgStatuses.MESSAGE_FROM_CLIENT.value} {message}'
                self.send(message)

    async def init_connection(self):
        loop = asyncio.get_running_loop()

        on_con_lost = loop.create_future()
        on_name_chosen = loop.create_future()

        try:
            self.transport, _ = await loop.create_connection(
                lambda: ChatClientProtocol(on_con_lost, on_name_chosen),
                self.server_host,
                self.server_port
            )
        except (ConnectionRefusedError, OSError):
            print('ERROR')
            print(f'Can\'t connect to the server {self.server_host}:{self.server_port}')
            loop.stop()
            return

        try:
            await on_name_chosen
        finally:
            self.name_chosen = True

        try:
            await on_con_lost
        finally:
            self.transport.close()

    def connect(self):
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, raise_graceful_exit)
        loop.add_signal_handler(signal.SIGTERM, raise_graceful_exit)
        loop.create_task(self.init_connection())
        loop.run_in_executor(None, self.input_func)

        try:
            loop.run_forever()
        except GracefulExit:
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

    server = Client(server_host=server_host, server_port=server_port)
    server.connect()
