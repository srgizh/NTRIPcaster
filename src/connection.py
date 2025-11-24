#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import json
import threading
from threading import Lock, RLock, Thread
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

from . import config
from . import logger
from .logger import log_system_event, log_error, log_warning, log_info, log_debug
from .rtcm2_manager import parser_manager as rtcm_manager  # Импорт менеджера парсинга RTCM2

@dataclass
class MountInfo:
    """Класс данных информации о точке монтирования"""
    mount_name: str
    ip_address: str = ""
    user_agent: str = ""
    protocol_version: str = "1.0"
    connect_time: float = field(default_factory=time.time)
    connect_datetime: str = field(default_factory=lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    last_update: float = field(default_factory=time.time)
    
    # Добавление ссылки на socket для принудительного закрытия подключения
    client_socket: Optional[object] = None
    
    # Информация о базовой станции
    station_id: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    height: Optional[float] = None
    
    # Географическая информация
    country: Optional[str] = None  # Код страны (например CHN)
    city: Optional[str] = None     # Название города (например Beijing)
    
    # Статистика данных
    total_bytes: int = 0
    total_messages: int = 0
    data_rate: float = 0.0
    data_count: int = 0
    last_data_time: Optional[float] = None
    
    # Информация о состоянии
    status: str = 'online'  # 'online', 'offline'
    
    # Информация о таблице STR
    str_data: str = ""
    initial_str_generated: bool = False
    final_str_generated: bool = False
    
    custom_info: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def uptime(self) -> float:
        """Время работы (секунды)"""
        return time.time() - self.connect_time
    
    @property
    def idle_time(self) -> float:
        """Время простоя (секунды)"""
        if self.last_data_time:
            return time.time() - self.last_data_time
        return self.uptime
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в формат словаря для JSON сериализации"""
        
        return {
            'mount_name': self.mount_name,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'protocol_version': self.protocol_version,
            'connect_time': self.connect_time,
            'connect_datetime': self.connect_datetime,
            'last_update': self.last_update,
            'station_id': self.station_id,
            'lat': self.lat,
            'lon': self.lon,
            'height': self.height,
            'country': self.country,
            'city': self.city,
            'total_bytes': self.total_bytes,
            'total_messages': self.total_messages,
            'data_rate': self.data_rate,
            'data_count': self.data_count,
            'last_data_time': self.last_data_time,
            'status': self.status,
            'str_data': self.str_data,
            'initial_str_generated': self.initial_str_generated,
            'final_str_generated': self.final_str_generated,
            'custom_info': self.custom_info
        }
class ConnectionManager:
    """Менеджер подключений и точек монтирования - унифицированное управление онлайн точками монтирования, подключениями пользователей и таблицей STR"""
    
    def __init__(self):
        # Таблица онлайн точек монтирования: {mount_name: MountInfo}
        self.online_mounts: Dict[str, MountInfo] = {}
        # Таблица онлайн пользователей: {user_id: [connection_info, ...]}
        self.online_users = defaultdict(list)
        # Счетчик подключений пользователей: {username: count}
        self.user_connection_count = defaultdict(int)
        # Счетчик точек монтирования: {mount_name: count}
        self.mount_connection_count = defaultdict(int)
        # Статистическая информация
        self.total_connections = 0
        self.rejected_connections = 0
        self.clients = {}  # Активные клиенты
        
        self.mount_lock = RLock()
        self.user_lock = RLock()
        
        
    def print_active_connections(self):
        """Вывод информации о всех текущих активных подключениях NTRIP в реальном времени"""
        with self.mount_lock:
            # print("\n=== Текущее состояние активных подключений NTRIP ===")
            # print(f"Общее количество активных точек монтирования: {len(self.online_mounts)}")
            
            # if not self.online_mounts:
            #     print("В данный момент нет активных подключений к точкам монтирования")
            # else:
            #     for mount_name, mount_info in self.online_mounts.items():
            #         uptime = mount_info.uptime
            #         print(f"Точка монтирования: {mount_name} | IP: {mount_info.ip_address} | Длительность подключения: {uptime:.1f} секунд | Состояние: {mount_info.status}")
            
            # print(f"Общее количество активных подключений пользователей: {len(self.online_users)}")
            # for username, connections in self.online_users.items():
            #     for conn_info in connections:
            #         print(f"Пользователь: {username} | ID подключения: {conn_info.get('connection_id', 'N/A')} | IP: {conn_info.get('ip_address', 'N/A')} | Точка монтирования: {conn_info.get('mount_name', 'N/A')}")
            
            # Вывод подробной статистики подключений
            # print(f"Общее количество подключений: {self.total_connections}, Отклоненных подключений: {self.rejected_connections}")
            
            # print("=== Вывод состояния подключений завершен ===\n")
            pass
    
    def force_refresh_connections(self):
        """Принудительное обновление состояния подключений и вывод подробной информации"""
        # print("\n=== Принудительное обновление состояния подключений ===")
        # print(f"Текущее время: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
        # Проверка валидности подключений к точкам монтирования
        invalid_mounts = []
        for mount_name, mount_info in self.online_mounts.items():
            idle_time = mount_info.idle_time
            if idle_time > 60:  # Более 60 секунд без данных
                invalid_mounts.append(mount_name)
                # print(f">>> Предупреждение: Точка монтирования {mount_name} находится в простое {idle_time:.1f} секунд")
        self.print_active_connections()
    
    def cleanup_zombie_connections(self):
        """Очистка зомби-подключений - проверка состояния socket на уровне системы"""
        import subprocess
        import re
        
        try:
            # Получение состояния socket подключений на уровне системы
            result = subprocess.run(['netstat', '-an'], capture_output=True, text=True, shell=True)
            if result.returncode != 0:
                log_warning("Невозможно получить состояние системных socket")
                return
            
            # Парсинг установленных подключений ESTABLISHED
            established_ips = set()
            for line in result.stdout.split('\n'):
                if ':2101' in line and 'ESTABLISHED' in line:
                    # Извлечение удаленного IP адреса
                    match = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)\s+ESTABLISHED', line)
                    if match:
                        remote_ip = match.group(1)
                        established_ips.add(remote_ip)
            
            # Проверка состояния подключений на уровне приложения
            with self.mount_lock:
                zombie_mounts = []
                for mount_name, mount_info in self.online_mounts.items():
                    if mount_info.ip_address not in established_ips:
                        zombie_mounts.append(mount_name)
                        log_warning(f"Обнаружено зомби-подключение: Точка монтирования {mount_name}, IP {mount_info.ip_address}")
                
                # Очистка зомби-подключений
                for mount_name in zombie_mounts:
                    log_info(f"Очистка зомби-подключения: {mount_name}")
                    self.remove_mount_connection(mount_name, "Очистка зомби-подключений")
                
                if zombie_mounts:
                    log_info(f"Очищено зомби-подключений: {len(zombie_mounts)}")
                else:
                    log_debug("Зомби-подключения не обнаружены")
                    
        except Exception as e:
            log_error(f"Исключение при очистке зомби-подключений: {e}", exc_info=True)
    
    def add_mount_connection(self, mount_name, ip_address, user_agent="", protocol_version="1.0", client_socket=None):
        """Добавление подключения точки монтирования (загрузка данных)"""
        with self.mount_lock:
            if mount_name in self.online_mounts:
                log_debug(f"Точка монтирования {mount_name} все еще в таблице потоков, возможно, это процесс очистки повторного подключения с того же IP")
               
                del self.online_mounts[mount_name]
            
            log_debug(f"Начало создания подключения точки монтирования - Имя: {mount_name}, IP: {ip_address}, User-Agent: {user_agent}, Версия протокола: {protocol_version}")
            
            # Создание информации о точке монтирования
            mount_info = MountInfo(
                mount_name=mount_name,
                ip_address=ip_address,
                user_agent=user_agent,
                protocol_version=protocol_version,
                client_socket=client_socket
            )
            
            # Добавление в таблицу онлайн точек монтирования
            self.online_mounts[mount_name] = mount_info
            log_debug(f"Точка монтирования {mount_name} добавлена в онлайн список, текущее количество онлайн точек монтирования: {len(self.online_mounts)}")
            
            # Генерация начальной таблицы STR
            self._generate_initial_str(mount_name)
            
            # Запуск процесса парсинга для исправления STR
            self.start_str_correction(mount_name)
            
            log_info(f"Точка монтирования {mount_name} онлайн, IP: {ip_address}, текущее количество онлайн точек монтирования: {len(self.online_mounts)}")
            log_debug(f"Подключение точки монтирования {mount_name} успешно, начальное состояние: {mount_info.status}, время подключения: {mount_info.connect_datetime}")
            
            self.print_active_connections()
            
            return True, "Mount point connected successfully"
    
    def remove_mount_connection(self, mount_name, reason="Принудительное отключение"):
        """Удаление подключения точки монтирования (отключение загрузки данных)"""
        with self.mount_lock:
            if mount_name in self.online_mounts:
                mount_info = self.online_mounts[mount_name]
                
                # Принудительное закрытие socket
                if mount_info.client_socket:
                    try:
                        mount_info.client_socket.close()
                        log_info(f"Принудительно закрыто socket подключение точки монтирования {mount_name}")
                    except Exception as e:
                        log_warning(f"Ошибка при закрытии socket подключения точки монтирования {mount_name}: {e}")
                
                # Запись информации об отключении
                log_debug(f"Точка монтирования {mount_name} отключена, детали: {reason}, состояние: {mount_info.status}, общее количество байт: {mount_info.total_bytes}, скорость данных: {mount_info.data_rate:.2f} Б/с")
                log_debug(f"Статистика точки монтирования {mount_name} - Общее количество сообщений: {mount_info.total_messages}, Количество пакетов данных: {mount_info.data_count}, Время простоя: {mount_info.idle_time:.1f} секунд")
                
                # Определение причины отключения для отладки
                if mount_info.status == "online":
                    actual_reason = reason if reason != "Принудительное отключение" else "Нормальное отключение"
                else:
                    actual_reason = "Аномальный оффлайн"
                
                del self.online_mounts[mount_name]
                
                log_info(f"Точка монтирования {mount_name} оффлайн, длительность подключения: {mount_info.uptime:.1f} секунд, причина: {actual_reason}")
                log_debug(f"Удаление точки монтирования {mount_name} завершено, оставшееся количество онлайн точек монтирования: {len(self.online_mounts)}")
                self.print_active_connections()
                
                return True
            else:
                log_debug(f"Попытка удалить несуществующую точку монтирования: {mount_name}")
                return False
    
    def _generate_initial_str(self, mount_name: str):
        """Генерация начальной таблицы STR"""
        parse_result = {}  
        self._process_str_data(mount_name, parse_result, mode="initial")
    def _update_message_statistics(self, mount_name: str, parsed_messages, data_size: int) -> bool:
        """Обновление базовой статистики точки монтирования"""
        if mount_name not in self.online_mounts:
            log_debug(f"Обновление статистики не удалось - Точка монтирования {mount_name} не онлайн")
            return False
        
        mount_info = self.online_mounts[mount_name]
        current_time = time.time()
        old_total_bytes = mount_info.total_bytes
        old_data_rate = mount_info.data_rate
        
        with self.mount_lock:
            
            mount_info.last_update = current_time
            mount_info.last_data_time = current_time
            mount_info.total_bytes += data_size
            mount_info.data_count += 1
            
            uptime = mount_info.uptime
            if uptime > 0:
                mount_info.data_rate = mount_info.total_bytes / uptime
            
            # Удалены частые debug логи обновления статистики, чтобы избежать перегрузки
            # log_debug(f"Обновление статистики точки монтирования {mount_name}: Размер пакета данных={data_size}Б, Накопленные байты={mount_info.total_bytes}Б (увеличение на {data_size}Б), Скорость данных={mount_info.data_rate:.2f}Б/с (было {old_data_rate:.2f}Б/с)")
            # log_debug(f"Обновление счетчика точки монтирования {mount_name}: Количество пакетов данных={mount_info.data_count}, Время работы={uptime:.1f} секунд, Время простоя={mount_info.idle_time:.1f} секунд")
        
        return True
    
    def update_mount_data(self, mount_name: str, data_size: int) -> bool:
        """Обновление статистики данных точки монтирования"""
        if mount_name not in self.online_mounts:
            return False
        
        return self._update_message_statistics(mount_name, None, data_size)
    
    def get_mount_str_data(self, mount_name: str) -> Optional[str]:
        """Получение данных таблицы STR точки монтирования"""
        if mount_name in self.online_mounts:
            return self.online_mounts[mount_name].str_data
        return None
    
    def get_all_str_data(self) -> Dict[str, str]:
        """Получение данных таблицы STR всех точек монтирования"""
        str_data = {}
        with self.mount_lock:
            for mount_name, mount_info in self.online_mounts.items():
                if mount_info.str_data:
                    str_data[mount_name] = mount_info.str_data
        return str_data

    
    def add_user_connection(self, username, mount_name, ip_address, user_agent="", protocol_version="1.0", client_socket=None):
        """Добавление подключения пользователя"""
        with self.user_lock:
            connection_id = f"{username}_{mount_name}_{int(time.time())}"
            
            socket_info = "Нет socket" if client_socket is None else f"Порт:{getattr(client_socket, 'getpeername', lambda: ('Неизвестно', 'Неизвестно'))()[1] if hasattr(client_socket, 'getpeername') else 'Неизвестно'}"
            log_debug(f"Создание подключения пользователя - Пользователь: {username}, Точка монтирования: {mount_name}, IP: {ip_address}, {socket_info}, User-Agent: {user_agent}")
            
            connection_info = {
                'connection_id': connection_id,
                'username': username,
                'mount_name': mount_name,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'protocol_version': protocol_version,
                'connect_time': time.time(),
                'connect_datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'last_activity': time.time(),
                'bytes_sent': 0,
                'client_socket': client_socket
            }
            
            if username not in self.online_users:
                self.online_users[username] = []
                log_debug(f"Создание списка подключений для нового пользователя {username}")
            if username not in self.user_connection_count:
                self.user_connection_count[username] = 0
            if mount_name not in self.mount_connection_count:
                self.mount_connection_count[mount_name] = 0
            
            old_user_count = self.user_connection_count[username]
            old_mount_count = self.mount_connection_count[mount_name]
            
            self.online_users[username].append(connection_info)
            self.user_connection_count[username] += 1
            self.mount_connection_count[mount_name] += 1
            
            log_info(f"Пользователь {username} IP: {ip_address} подключен, начата подписка на данные RTCM от точки монтирования {mount_name}")
            log_debug(f"Обновление статистики подключений пользователя - Пользователь {username}: {old_user_count} -> {self.user_connection_count[username]}, Точка монтирования {mount_name}: {old_mount_count} -> {self.mount_connection_count[mount_name]}")
            log_debug(f"Сгенерирован ID подключения: {connection_id}, Общее количество онлайн пользователей: {len(self.online_users)}")
            return connection_id
    
    def remove_user_connection(self, username, connection_id=None, mount_name=None):
        """Удаление подключения пользователя"""
        with self.user_lock:
            if username not in self.online_users:
                return False
            
            connections_to_remove = []
            
            for i, conn in enumerate(self.online_users[username]):
                should_remove = False
                
                if connection_id and conn['connection_id'] == connection_id:
                    should_remove = True
                elif mount_name and conn['mount_name'] == mount_name:
                    should_remove = True
                elif not connection_id and not mount_name:
                    should_remove = True
                
                if should_remove:
                    connections_to_remove.append(i)
                    self.mount_connection_count[conn['mount_name']] -= 1
                    
                    
                    if conn.get('client_socket'):
                        try:
                            conn['client_socket'].close()
                        except:
                            pass
                    
                    log_info(f"Пользователь {username} отключен от точки монтирования {conn['mount_name']}")
            

            for i in reversed(connections_to_remove):
                del self.online_users[username][i]
                self.user_connection_count[username] -= 1
            
            if not self.online_users[username]:
                del self.online_users[username]
                del self.user_connection_count[username]
            
            return len(connections_to_remove) > 0
    
    def update_mount_data_stats(self, mount_name, data_size):
        """Обновление статистики данных точки монтирования"""
        if mount_name in self.online_mounts:
            mount_info = self.online_mounts[mount_name]
            mount_info.data_count += 1
            mount_info.last_data_time = time.time()
            mount_info.total_bytes += data_size
            uptime = mount_info.uptime
            if uptime > 0:
                mount_info.data_rate = mount_info.total_bytes / uptime
    
    def update_user_activity(self, username, connection_id, bytes_sent=0):
        """Обновление состояния пользователя"""
        with self.user_lock:
            if username not in self.online_users:
                log_debug(f"Обновление состояния пользователя не удалось - Пользователь {username} не онлайн")
                return False
            
            connection_found = False
            for conn in self.online_users[username]:
                if conn['connection_id'] == connection_id:
                    old_bytes = conn['bytes_sent']
                    conn['last_activity'] = time.time()
                    conn['bytes_sent'] += bytes_sent
                    connection_found = True
                    
                    # Удалены частые debug логи обновления активности пользователя, чтобы избежать перегрузки
                    # if bytes_sent > 0:
                    #     log_debug(f"Обновление информации пользователя {username}: ID подключения={connection_id}, Отправлено в этот раз={bytes_sent}Б, Накопленная отправка={conn['bytes_sent']}Б (было {old_bytes}Б), Точка монтирования={conn['mount_name']}")
                    break
            
            if not connection_found:
                log_debug(f"Обновление состояния пользователя не удалось - ID подключения {connection_id} не существует для пользователя {username}")
                return False
            
            return True
    
    def is_mount_online(self, mount_name):
        """Проверка, находится ли точка монтирования онлайн"""
        with self.mount_lock:
            return mount_name in self.online_mounts
    
    def get_user_connection_count(self, username):
        """Получение количества подключений пользователя"""
        return self.user_connection_count.get(username, 0)
    
    def get_user_connect_time(self, username):
        """Получение времени последнего подключения пользователя"""
        with self.user_lock:
            if username in self.online_users and self.online_users[username]:
                
                latest_connection = max(self.online_users[username], key=lambda x: x['connect_time'])
                return latest_connection['connect_datetime']
            return None
    
    def get_mount_connection_count(self, mount_name):
        """Получение количества подключений точки монтирования"""
        return self.mount_connection_count.get(mount_name, 0)
    
    def get_online_mounts(self):
        """Получение списка онлайн точек монтирования"""
        with self.mount_lock:
            return {name: info.to_dict() for name, info in self.online_mounts.items()}
    
    def get_online_users(self):
        """Получение списка онлайн пользователей"""
        with self.user_lock:
            return dict(self.online_users)
    
    def get_mount_info(self, mount_name):
        """Получение информации о точке монтирования"""
        if mount_name in self.online_mounts:
            return self.online_mounts[mount_name].to_dict()
        return None
    
    def get_user_connections(self, username):
        """Получение информации о подключениях пользователя"""
        return self.online_users.get(username, [])
    
    def get_mount_statistics(self, mount_name: str) -> Optional[Dict[str, Any]]:
        """Получение статистики точки монтирования"""
        if mount_name not in self.online_mounts:
            return None
        
        mount_info = self.online_mounts[mount_name]
        return {
            'mount_name': mount_name,
            'status': mount_info.status,
            'uptime': mount_info.uptime,
            'total_bytes': mount_info.total_bytes,
            'data_rate': mount_info.data_rate,
            'data_count': mount_info.data_count
        }
    
    def generate_mount_list(self):
        """Генерация данных списка точек монтирования"""
        mount_list = []
        
        with self.mount_lock:
            for mount_name, mount_info in self.online_mounts.items():
               
                if mount_info.str_data:
                    mount_list.append(mount_info.str_data)

                else:
                    # Генерация информации в формате NTRIP по умолчанию
                    mount_data = [
                        'STR',
                        mount_name, # Имя точки монтирования
                        'none',  # Название города или другое описание, по умолчанию none
                        'RTCM 3.3',  # format
                        '1005(10)',  # format_details
                        '0',  # carrier
                        'GPS',  # nav_system
                        '2RTK',  # network
                        'CHN',  # country
                        str(mount_info.lat) if mount_info.lat is not None else '0.0',  # latitude
                        str(mount_info.lon) if mount_info.lon is not None else '0.0',  # longitude
                        '0',  # nmea
                        '0',  # solution
                        mount_info.user_agent or 'unknown',  # generator
                        'N',  # compression
                        'B',  # authentication
                        'N',  # fee
                        '500',  # bitrate
                        'NO'  # misc
                    ]
                    mount_info_str = ';'.join(mount_data)
                    mount_list.append(mount_info_str)
                    log_info(f"Создана таблица STR для точки монтирования {mount_name}: {mount_info_str}", 'connection_manager')
        
        return mount_list
    
    def get_statistics(self):
        """Получение общей статистики"""
        with self.mount_lock, self.user_lock:
            total_mounts = len(self.online_mounts)
            total_users = sum(len(connections) for connections in self.online_users.values())
            
            mount_stats = []
            for mount_name, mount_info in self.online_mounts.items():
                mount_stats.append({
                    'mount_name': mount_name,
                    'ip_address': mount_info.ip_address,
                    'uptime': mount_info.uptime,
                    'data_count': mount_info.data_count,
                    'total_bytes': mount_info.total_bytes,
                    'total_messages': mount_info.total_messages,
                    'data_rate': mount_info.data_rate,
                    'user_count': self.mount_connection_count.get(mount_name, 0),
                    'status': mount_info.status,
                    'str_generated': mount_info.final_str_generated
                })
            
            user_stats = []
            for username, connections in self.online_users.items():
                for conn in connections:
                    user_stats.append({
                        'username': username,
                        'mount_name': conn['mount_name'],
                        'ip_address': conn['ip_address'],
                        'connect_time': conn['connect_time'],
                        'bytes_sent': conn['bytes_sent']
                    })
            
            return {
                'total_mounts': total_mounts,
                'total_users': total_users,
                'mounts': mount_stats,
                'users': user_stats
            }
    
    def start_str_correction(self, mount_name: str):
        """Запуск 30-секундного парсинга RTCM и исправление STR"""
        if mount_name not in self.online_mounts:
            log_warning(f"Невозможно запустить исправление STR, точка монтирования {mount_name} не онлайн")
            return

        success = rtcm_manager.start_parser(
            mount_name=mount_name,
            mode="str_fix",
            duration=30
        )
        
        if not success:
            log_error(f"Ошибка при запуске парсинга исправления STR для точки монтирования {mount_name}")
            return
            
        log_info(f"Запущен парсинг исправления STR для точки монтирования {mount_name}, таблица STR будет исправлена через 30 секунд")
        
        
        def wait_and_correct():
            log_debug(f"Начало ожидания завершения исправления STR для точки монтирования {mount_name}")
            time.sleep(35)  
            log_debug(f"Ожидание завершено, начало получения результатов парсинга для точки монтирования {mount_name}")
            
            parse_result = rtcm_manager.get_result(mount_name)
            log_debug(f"Получены результаты парсинга для точки монтирования {mount_name}: {parse_result is not None}")
            
            if parse_result:
                log_debug(f"Содержимое результатов парсинга для точки монтирования {mount_name}: {parse_result}")
                
                self._process_str_data(mount_name, parse_result, mode="correct")
            else:
                log_warning(f"Не получены результаты парсинга исправления STR для точки монтирования {mount_name}")
                log_debug(f"Исправление STR не удалось - Точка монтирования: {mount_name}, возможные причины: таймаут парсинга, недостаточно данных или ошибка парсера")
            
            
            log_debug(f"Остановка парсера для точки монтирования {mount_name}")
            rtcm_manager.stop_parser(mount_name)
            log_debug(f"Процесс исправления STR завершен для точки монтирования {mount_name}")
        
        threading.Thread(target=wait_and_correct, daemon=True).start()

    def _process_str_data(self, mount_name: str, parse_result: dict, mode: str = "correct"):
        """Унифицированная функция обработки STR: поддерживает режимы начальной генерации, исправления и повторной генерации
        
        Args:
            mount_name: Имя точки монтирования
            parse_result: Словарь результатов парсинга
            mode: Режим обработки - "initial"(начальная генерация), "correct"(исправление), "regenerate"(повторная генерация)
        """
        log_debug(f"Начало обработки STR для точки монтирования {mount_name}, режим: {mode}")
        log_debug(f"Детали результатов парсинга: {parse_result}")
        
        with self.mount_lock:
           
            if mount_name not in self.online_mounts:
                log_debug(f"Точка монтирования {mount_name} не онлайн, невозможно обработать STR")
                return
            
            mount_info = self.online_mounts[mount_name]
            original_str = mount_info.str_data
            
            if mode == "initial":
                
                str_parts = self._create_initial_str_parts(mount_name, parse_result)
            elif mode in ["correct", "regenerate"]:
                
                if not original_str:
                    log_warning(f"У точки монтирования {mount_name} нет начальных данных STR, переключение на режим начальной генерации")
                    str_parts = self._create_initial_str_parts(mount_name, parse_result)
                else:
                    log_debug(f"Оригинальная STR для точки монтирования {mount_name}: {original_str}")
                    str_parts = original_str.split(';')
                    if len(str_parts) < 19:
                        log_error(f"Ошибка формата STR, невозможно обработать для точки монтирования {mount_name} - Количество полей: {len(str_parts)}, Ожидается: 19")
                        return
                    
                    self._update_str_fields(str_parts, parse_result, mode)
            else:
                log_error(f"Неизвестный режим обработки STR: {mode}")
                return
            
            processed_str = ";".join(str_parts)
            log_debug(f"Обработанная STR для точки монтирования {mount_name}: {processed_str}")
           
            
            mount_info.str_data = processed_str
            if mode == "initial":
                mount_info.initial_str_generated = True
            else:
                mount_info.final_str_generated = True
            
            if mode == "correct":
                if original_str != processed_str:
                    log_info(f"STR для {mount_name} исправлена: {processed_str}")

                else:
                    log_info(f"Исправление таблицы STR завершено для точки монтирования {mount_name}, обновление не требуется")
                    log_info(f"Текущая STR: {processed_str}")
            elif mode == "initial":
                log_info(f"STR для точки монтирования {mount_name} сгенерирована: {processed_str}")
            
            log_debug(f"Процесс обработки STR завершен для точки монтирования {mount_name}, режим: {mode}, финальное состояние: final_str_generated={mount_info.final_str_generated}")
    
    
    def _create_initial_str_parts(self, mount_name: str, parse_result: dict) -> list:
        """Создание списка полей начальной STR"""
        from . import config
        
        mount_info = self.online_mounts[mount_name]
        app_author = config.APP_AUTHOR.replace(' ', '') if config.APP_AUTHOR else '2rtk'
        
        identifier = parse_result.get("city") or mount_info.city or "none"
        country_code = parse_result.get("country") or mount_info.country or config.CASTER_COUNTRY
        latitude = parse_result.get("lat") or config.CASTER_LATITUDE
        longitude = parse_result.get("lon") or config.CASTER_LONGITUDE

        str_parts = [
            "STR",                          # 0: type
            mount_name,                     # 1: mountpoint
            identifier,                     # 2: identifier
            "RTCM3.x",                     # 3: format
            parse_result.get("message_types_str", "1005"),  # 4: format-details
            "0",                           # 5: Здесь я не использую стандарт RTCM, использую информацию о частотных диапазонах после статистики
            parse_result.get("gnss_combined", "GPS"),       # 6: nav-system
            app_author,                     # 7: network
            country_code,                   # 8: country
            f"{latitude:.4f}",             # 9: latitude
            f"{longitude:.4f}",            # 10: longitude
            "0",                           # 11: nmea
            "0",                           # 12: solution
            "2RTK_NtirpCaster",           # 13: generator
            "N",                           # 14: compression
            "B",                           # 15: authentication
            "N",                           # 16: fee
            "500",                         # 17: bitrate (здесь способ расчета в RTCM.py имеет проблемы, нужно исправить позже)
            "NO"                           # 18: misc
        ]
        
        self._update_str_fields(str_parts, parse_result, "initial")
        
        return str_parts
    
    def _update_str_fields(self, str_parts: list, parse_result: dict, mode: str = "correct"):
        """Обновление полей STR на основе результатов парсинга
        
        Args:
            str_parts: Список полей STR
            parse_result: Словарь результатов парсинга
            mode: Режим обработки - "initial"(начальная генерация), "correct"(исправление), "regenerate"(повторная генерация)
        """
       
        if parse_result.get("city"):
            str_parts[2] = parse_result["city"]
        
       
        if parse_result.get("message_types_str"):
            str_parts[4] = parse_result["message_types_str"]
        
        
        if parse_result.get("carrier_combined"):
            carrier_info = parse_result["carrier_combined"]
            
            str_parts[5] = carrier_info  # Прямая вставка информации о фазе несущей, например L1、L1+L5+B1 и т.д. Не соответствует стандарту RTCM.
            #Справочник по стандартному формату STR: https://software.rtcm-ntrip.org/wiki/STR
        
        # 4. Обновление поля nav-system (7-е поле, навигационная система)
        if parse_result.get("gnss_combined"):
            str_parts[6] = parse_result["gnss_combined"]
        
        # 5. Обновление поля country (9-е поле, код страны)
        if parse_result.get("country"):
            # rtcm2.py уже выполнил преобразование из 2 символов в 3 символа, используем напрямую
            str_parts[8] = parse_result["country"]
        
        # 6. (10-е поле, широта)
        if parse_result.get("lat"):
            str_parts[9] = f"{parse_result['lat']:.4f}"
        
        # 7. (11-е поле, долгота)
        if parse_result.get("lon"):
            str_parts[10] = f"{parse_result['lon']:.4f}"
        
        # 8. (14-е поле)
        str_parts[13] = "2RTK_NtirpCaster"
        
        # 9. (17-е поле)
        str_parts[16] = "N"
        
        # 10. (18-е поле, битрейт)
        if parse_result.get("bitrate"):
            bitrate_bps = parse_result["bitrate"]  
            str_parts[17] = str(int(bitrate_bps))  
        
        # 11. Последнее поле таблицы STR. Изменяется на yes или no для определения, была ли STR исправлена
        if mode == "initial":
            str_parts[-1] = "NO"  # При начальной генерации помечается как непроверенная
        else:  # Режим correct или regenerate
            str_parts[-1] = "YES"  # После исправления помечается как проверенная

    def check_mount_exists(self, mount_name: str) -> bool:

        return mount_name in self.online_mounts
    

_connection_manager = None
_manager_lock = Lock()

#*****************************
# Управление подключениями - для дальнейшего расширения использовать API для управления состоянием подключений
#*****************************

def get_connection_manager():
    """Получение глобального экземпляра менеджера подключений"""
    global _connection_manager
    if _connection_manager is None:
        with _manager_lock:
            if _connection_manager is None:
                _connection_manager = ConnectionManager()
    return _connection_manager

def add_mount_connection(mount_name, ip_address, user_agent="", protocol_version="1.0"):
    """Добавление подключения точки монтирования"""
    return get_connection_manager().add_mount_connection(mount_name, ip_address, user_agent, protocol_version)

def remove_mount_connection(mount_name):
    """Удаление подключения точки монтирования"""
    return get_connection_manager().remove_mount_connection(mount_name)

def add_user_connection(username, mount_name, ip_address, user_agent="", protocol_version="1.0", client_socket=None):
    """Добавление подключения пользователя"""
    return get_connection_manager().add_user_connection(username, mount_name, ip_address, user_agent, protocol_version, client_socket)

def remove_user_connection(username, connection_id=None, mount_name=None):
    """Удаление подключения пользователя"""
    return get_connection_manager().remove_user_connection(username, connection_id, mount_name)

def update_user_activity(username, connection_id, bytes_sent=0):
    """Обновление активности пользователя"""
    return get_connection_manager().update_user_activity(username, connection_id, bytes_sent)

def is_mount_online(mount_name):
    """Проверка, находится ли точка монтирования онлайн"""
    return get_connection_manager().is_mount_online(mount_name)

def get_user_connection_count(username):
    """Получение количества подключений пользователя"""
    return get_connection_manager().get_user_connection_count(username)

def update_mount_data(mount_name, data_size):
    """Обновление данных точки монтирования"""
    return get_connection_manager().update_mount_data(mount_name, data_size)

def update_mount_data_stats(mount_name, data_size):
    """Обновление статистики данных точки монтирования"""
    return get_connection_manager().update_mount_data_stats(mount_name, data_size)

def get_statistics():
    """Получение статистики"""
    return get_connection_manager().get_statistics()

def get_mount_statistics(mount_name):
    """Получение статистики точки монтирования"""
    return get_connection_manager().get_mount_statistics(mount_name)

def generate_mount_list():
    """Генерация данных списка точек монтирования"""
    return get_connection_manager().generate_mount_list()

def check_mount_exists(mount_name):
    """Проверка существования точки монтирования"""
    return get_connection_manager().check_mount_exists(mount_name)
