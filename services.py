import json

from asyncio import BaseTransport
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List

# Нужен класс для списка сообщений

# Каждое сообщение должно иметь:
#  – Дата/время отправки
#  – Имя пользователя отправителя
#  – Кому отправлено (канал или персона)
#  – Кому конкретно отправлено (имя канала или персоны)
#  – Текст сообщения

# НЕ ОБЯЗАТЕЛЬНО: Журнал сообщений должен иметь методы для записи в файл и загрузки истории при старте сервера

EOS = b'\n'

CHANNEL = 'channel'
PRIVATE = 'private'
GENERAL = 'general'


class InfoMsgStatuses(Enum):
    CHOOSE_NAME = 'choose_name'
    NAME_ACCEPTED = 'name_accepted'
    NAME_REJECTED = 'name_rejected'

    GET_STATISTIC = 'get_statistic'
    SET_STATISTIC = 'set_statistic'

    MESSAGE_FROM_SRV = 'message_from_srv'
    MESSAGE_FROM_CLIENT = 'message_from_client'
    MESSAGE_APPROVE = 'message_approve'

    CHANGE_CHAT = 'change_chat'

    @property
    def msg_bts(self) -> bytes:
        return self.value.encode()


@dataclass
class MessageItem:
    """
    Объект одного сообщения
    """
    uuid: str  # TODO протестить создание UUID для каждого сообщения для того чтобы можно было ими управлять
    dt: datetime  # Если время больше времени текущего - считаем что это сообщение отложенное и его можно отменить
    creator: str
    destination_type: str
    destination_name: str
    message: str
    received_users: List  # Список пользователей которым данное сообщение было доставлено

    # TODO
    #   read_users: List – Список пользователей которые прочитали данное сообщение

    def serialize(self) -> str:

        msg = {
            'uuid': self.uuid,
            'creator': self.creator,
            'destination_type': self.destination_type,
            'destination_name': self.destination_name,
            'message': self.message
        }

        return json.dumps(msg)


class MessagePool:
    __pool = []

    def add(self, msg: MessageItem):
        self.__pool.append(msg)

    @property
    def count(self) -> int:
        return len(self.__pool)

    def serialize(self):
        return json.dumps([item.message for item in self.__pool], ensure_ascii=False).encode()

    def get_message_by_uuid(self, uuid: str) -> Optional[MessageItem]:
        msgs = filter(lambda msg: msg.uuid == uuid, self.__pool)
        try:
            item = next(msgs)
        except StopIteration:
            item = None
        return item

    def get_messages(self,
                     creator: Optional[str] = None,
                     destination_type: str = CHANNEL,
                     destination_name: str = GENERAL
                     ) -> List[MessageItem]:

        """
        Получить все сообщения с заданными параметрами
        """

        now = datetime.now()
        msgs = list(
            filter(
                lambda msg: msg.dt < now
                            and msg.destination_type == destination_type
                            and msg.destination_name == destination_name,
                self.__pool
            )
        )

        return msgs


@dataclass
class ConnectionItem:
    """
    Объект одного подключения
    """
    transport: BaseTransport
    user_name: Optional[str]  # Имя пользователя
    current_connection_type = CHANNEL
    current_connection_name = GENERAL

    #  TODO
    #   Список пользователей которые пожаловались на данного пользователя
    #   Время, до которого пользователь забанен


class ConnectionPool:
    __pool = []

    def add(self, con: ConnectionItem) -> None:
        self.__pool.append(con)

    @property
    def pool_len(self) -> int:
        return len(self.__pool)

    def get_all_user_names(self) -> List[str]:
        return [item.user_name for item in self.__pool]

    def get_all_channel_names(self) -> List:
        # For future, now channels are not maintain
        return list(
            set(
                item.current_connection_name for item in self.__pool if item.current_connection_type == CHANNEL
            ))

    def get_all_transports(self) -> List[BaseTransport]:
        return [item.transport for item in self.__pool]

    def get_all_transports_with_name(self) -> List[BaseTransport]:
        return [item.transport for item in self.__pool if item.user_name]

    def get_by_transport(self, transport: BaseTransport) -> Optional[ConnectionItem]:
        item_gen = filter(lambda x: x.transport == transport, self.__pool)
        try:
            item = next(item_gen)
        except StopIteration:
            item = None
        return item

    def get_by_user_name(self, user_name: str) -> Optional[ConnectionItem]:
        item_gen = filter(lambda x: x.user_name == user_name, self.__pool)
        try:
            item = next(item_gen)
        except StopIteration:
            item = None
        return item

    def del_by_transport(self, transport: BaseTransport) -> None:
        item = self.get_by_transport(transport)
        self.__pool.remove(item)

    def send_message(self, msg_item: MessageItem) -> None:
        """
        Отправляем текстовое сообщение всем участникам чата
        """
        sender = self.get_by_user_name(msg_item.creator)
        message = f'{InfoMsgStatuses.MESSAGE_FROM_SRV.value} {msg_item.serialize()}\n'.encode()

        # FIXME  при рассылке сообщений необходимо учитывать чтобы сообщения отправлялись только тем
        #  пользователям которые на данный момент находятся в одной комнате с пользователем
        for connection in self.__pool:
            if connection != sender:
                connection.transport.write(message)
