import asyncio
import json

from services import InfoMsgStatuses, CHANNEL, GENERAL, PRIVATE


# Хороший пример подключения клиента к серверу
# https://stackoverflow.com/a/69255838

class ChatClientProtocol(asyncio.Protocol):
    def __init__(self, on_con_lost, on_name_chosen):
        self.on_con_lost = on_con_lost
        self.on_name_chosen = on_name_chosen
        self.statistic = None  # {'users': ['FIL', 'NIC'], 'channels': ['general']}
        self.own_name = None
        self.transport = None

        # At the start, we connect a user to the default channel
        self.current_connection_type = CHANNEL
        self.current_connection_name = GENERAL

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        operator, *args = data.decode().strip().split(' ', 1)

        if operator == InfoMsgStatuses.CHOOSE_NAME.value:
            print('Choose username')

        elif operator == InfoMsgStatuses.NAME_REJECTED.value:
            print('This username is already in use\nPlease choose another one')

        elif operator == InfoMsgStatuses.NAME_ACCEPTED.value:
            self.own_name = args[0]
            print(f'OK! Your name is {self.own_name}')
            self.transport.write(InfoMsgStatuses.GET_STATISTIC.msg_bts)
            self.on_name_chosen.set_result(True)

        elif operator == InfoMsgStatuses.CHANGE_CHAT.value:
            chat_type, chat_name = args[0].strip().split(' ', 1)
            self.current_connection_type = chat_type
            self.current_connection_name = chat_name
            print(f'Current chat type: {self.current_connection_type}, '
                  f'and connection name: {self.current_connection_name}')

        elif operator == InfoMsgStatuses.SET_STATISTIC.value:
            self.statistic = json.loads(args[0])

        elif operator == InfoMsgStatuses.MESSAGE_FROM_SRV.value:

            try:
                msg_text = args[0]
            except IndexError:
                # TODO log
                return

            msg = json.loads(msg_text)
            uuid = msg['uuid']
            creator = msg['creator']
            destination_type = msg['destination_type']
            destination_name = msg['destination_name']

            # If a user situating at the correct channel - printing and sending a signal
            #   about the message has been read

            if (
                    (
                            destination_type == CHANNEL
                            and self.current_connection_type == destination_type
                            and self.current_connection_name == destination_name
                    ) or
                    (
                            destination_type == PRIVATE
                            and self.current_connection_type == destination_type
                            and self.own_name == destination_name
                            and self.current_connection_name == creator
                    )
            ):
                message = msg['message']
                print(f'[{creator}] {message}')

                msg_to_srv = {
                    'uuid': uuid,
                    'user': self.own_name
                }

                approval_to_srv = f'{InfoMsgStatuses.MESSAGE_APPROVE.value} {json.dumps(msg_to_srv)}'.encode()
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
            message = input()
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

            elif command == 'show_statistic':
                # TODO Показываем статистику
                ...

            elif command == 'ban_user':
                # TODO Баним пользователя
                ...

            else:
                message = f'{InfoMsgStatuses.MESSAGE_FROM_CLIENT.value} {message}'
                self.send(message)

    async def init_connection(self):
        loop = asyncio.get_running_loop()
        on_con_lost = loop.create_future()
        on_name_chosen = loop.create_future()

        self.transport, _ = await loop.create_connection(
            lambda: ChatClientProtocol(on_con_lost, on_name_chosen),
            self.server_host,
            self.server_port
        )

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
        loop.create_task(self.init_connection())
        loop.run_in_executor(None, self.input_func)

        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    server = Client(server_host='127.0.0.1', server_port=8000)
    server.connect()
