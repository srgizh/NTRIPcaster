#!/usr/bin/env python3
"""
ntrip.py - NTRIP Caster основной модуль
Функции: прослушивание NTRIP запросов, прием запросов на загрузку и скачивание, 
проверка валидности пользователей и точек монтирования
"""

import sys
import time
import socket
import logging
import threading
import base64
from datetime import datetime, timezone
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue, Full, Empty
from collections import defaultdict

from . import forwarder
from . import config
from . import logger
from .logger import log_debug, log_info, log_warning, log_error, log_critical, log_system_event
from . import connection


DEBUG = config.DEBUG
VERSION = config.VERSION
NTRIP_PORT = config.NTRIP_PORT
WEB_PORT = config.WEB_PORT
BUFFER_SIZE = config.BUFFER_SIZE


class AntiSpamLogger:
    def __init__(self, time_window=60, max_count=5):
        self.time_window = time_window  
        self.max_count = max_count      
        self.message_counts = defaultdict(list)  
        self.suppressed_counts = defaultdict(int)  
        self.lock = threading.Lock()
    
    def should_log(self, message_key):
        """Проверить, следует ли записывать лог"""
        with self.lock:
            now = time.time()

            self.message_counts[message_key] = [
                timestamp for timestamp in self.message_counts[message_key]
                if now - timestamp < self.time_window
            ]
            
            if len(self.message_counts[message_key]) < self.max_count:
                self.message_counts[message_key].append(now)
                return True
            else:
                self.suppressed_counts[message_key] += 1
                return False
    
    def get_suppressed_count(self, message_key):
        """Получить количество подавленных сообщений"""
        with self.lock:
            count = self.suppressed_counts[message_key]
            self.suppressed_counts[message_key] = 0  
            return count

anti_spam_logger = AntiSpamLogger(time_window=60, max_count=3)
MAX_CONNECTIONS = config.MAX_CONNECTIONS
MAX_CONNECTIONS_PER_USER = config.MAX_CONNECTIONS_PER_USER
MAX_WORKERS = config.MAX_WORKERS
CONNECTION_QUEUE_SIZE = config.CONNECTION_QUEUE_SIZE

# Получить логгер

class NTRIPHandler:
    """Обработчик NTRIP запросов"""
    
    def __init__(self, client_socket, client_address, db_manager):
        self.client_socket = client_socket
        self.client_address = client_address
        self.db_manager = db_manager
        self.ntrip_version = "1.0"
        self.protocol_type = "ntrip1_0"
        self.user_agent = ""
        self.mount = ""
        self.username = ""
        self.ntrip1_password = ""  
        self.current_method = "GET"  
        
        self.client_socket.settimeout(config.SOCKET_TIMEOUT)
        
        self._configure_keepalive()
    
    def _configure_keepalive(self):
        """Настроить TCP Keep-Alive (кроссплатформенная реализация)"""
        try:
            if not config.TCP_KEEPALIVE['enabled']:
                return
                
            # Включить TCP Keep-Alive 
            self.client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            try:
                if hasattr(socket, 'TCP_KEEPIDLE'):
                    self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, config.TCP_KEEPALIVE['idle'])
                if hasattr(socket, 'TCP_KEEPINTVL'):
                    self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, config.TCP_KEEPALIVE['interval'])
                if hasattr(socket, 'TCP_KEEPCNT'):
                    self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, config.TCP_KEEPALIVE['count'])
                
                message_key = "tcp_keepalive_configured"
                if anti_spam_logger.should_log(message_key):
                    suppressed = anti_spam_logger.get_suppressed_count(message_key)
                    if suppressed > 0:
                        logger.log_debug(f"TCP Keep-Alive настроен: idle={config.TCP_KEEPALIVE['idle']}s (подавлено {suppressed} похожих сообщений)", 'ntrip')
                    else:
                        logger.log_debug(f"TCP Keep-Alive настроен: idle={config.TCP_KEEPALIVE['idle']}s", 'ntrip')
            except OSError:

                logger.log_debug("TCP Keep-Alive включен (используются системные параметры по умолчанию)", 'ntrip')
        except Exception as e:
            logger.log_debug(f"Настройка Keep-Alive не удалась: {e}", 'ntrip')
    
    def handle_request(self):
        """Обработать NTRIP запрос с улучшенной валидацией и обработкой ошибок"""
        try:
            # Изменено на уровень debug, чтобы избежать частых логов
            log_debug(f"=== Начало обработки запроса {self.client_address} ===")

            request_data = self.client_socket.recv(BUFFER_SIZE).decode('utf-8', errors='ignore')
            if not request_data:
                log_debug(f"Клиент {self.client_address} отправил пустой запрос")
                return
            
            raw_request = request_data[:200]
            sanitized_request = self._sanitize_request_for_logging(raw_request)

            # Изменено на уровень debug, чтобы избежать частых логов
            log_debug(f"Обнаружен запрос на подключение от {self.client_address}: {sanitized_request}")
            
            lines = request_data.strip().split('\r\n')
            if not lines or not lines[0].strip():
                self.send_error_response(400, "Bad Request: Empty request line")
                return
            
            request_line = lines[0]
            try:
                method, path, protocol = self._parse_request_line(request_line)

                self.current_method = method.upper()
            except ValueError as e:
                log_debug(f"Не удалось распарсить строку запроса {self.client_address}: {e}")
                self.send_error_response(400, f"Bad Request: {str(e)}")
                return
            
            headers = self._parse_headers(lines[1:])
            
            if self._is_empty_request(method, path, headers):
                log_debug(f"Обнаружен пустой запрос {self.client_address}")
                self.send_error_response(400, "Bad Request: Empty request")
                return
            
            self._determine_ntrip_version(headers, request_line)
            
            # Для отладки: логируем определенный протокол
            log_debug(f"Определен протокол для {self.client_address}: {self.protocol_type} (версия: {self.ntrip_version}), метод: {method}, путь: {path}")
            
            is_valid, error_msg = self._is_valid_request(method, path, headers)
            if not is_valid:
                # Проверка не прошла - сохраняем уровень info, это важная информация
                log_info(f"Проверка запроса не прошла {self.client_address}: {error_msg} (протокол: {self.protocol_type})")
                self.send_error_response(400, f"Bad Request: {error_msg}")
                return
            
            self.user_agent = headers.get('user-agent', 'Unknown')
            
            # Изменено на уровень debug, чтобы избежать частых логов
            log_debug(f"Проверка запроса пройдена {self.client_address}: {method} {path} (протокол: {self.protocol_type})")

            if method.upper() in ['SOURCE', 'POST']:
                # Обработка загрузки данных
                self.handle_upload(path, headers)
            elif method.upper() == 'GET':
                # Обработка скачивания данных
                if self.protocol_type in ['ntrip1_0_http', 'ntrip2_0', 'ntrip1_0', 'ntrip0_8']:
                    self.handle_download(path, headers)
                else:
                    # Обработка обычного HTTP GET
                    self.handle_http_get(path, headers)

            elif method.upper() == 'OPTIONS':
                # Обработка OPTIONS запроса
                self.handle_options(headers)
            elif method.upper() in ['DESCRIBE', 'SETUP', 'PLAY', 'PAUSE', 'TEARDOWN', 'RECORD']:
                # Обработка RTSP команд
                self.handle_rtsp_command(method, path, headers)
            else:
                self.send_error_response(405, f"Method Not Allowed: {method}")
        
        except socket.timeout:
            log_debug(f"Клиент {self.client_address} - таймаут подключения")
            
            self._cleanup()
        except UnicodeDecodeError as e:
            log_debug(f"Не удалось декодировать запрос {self.client_address}: {e}")
            self.send_error_response(400, "Bad Request: Invalid encoding")
            # Очистка ресурсов
            self._cleanup()
        except Exception as e:
            log_error(f"Исключение при обработке запроса {self.client_address}: {e}", exc_info=True)
            self.send_error_response(500, "Internal Server Error")

            self._cleanup()
    
    def _parse_request_line(self, request_line):
        """Распарсить строку запроса, поддерживает различные форматы SOURCE для разных версий NTRIP"""
        parts = request_line.split()
        
        if not parts:
            raise ValueError("Empty request line")
        
        method = parts[0].upper()
        
        if method == 'SOURCE':
            if len(parts) >= 2:
                if len(parts) == 2:
                    # NTRIP 0.8 формат: "SOURCE <url>" или "SOURCE <path>"
                    url_or_path = parts[1]
                    if url_or_path.startswith('/') and not url_or_path.startswith(('http://', 'https://', 'rtsp://')):
                        # SOURCE /mountpoint без пароля, требуется последующая 401 аутентификация
                        return 'SOURCE', url_or_path, 'NTRIP/1.0'
                    else:
                        return self._parse_source_url_format(url_or_path)
                elif len(parts) >= 3:
                    password = parts[1]
                    mountpoint_or_url = parts[2]
                    
                    # Проверить, является ли это URL
                    if mountpoint_or_url.startswith(('http://', 'https://', 'rtsp://')):
                        # NTRIP 0.8 URL формат: "SOURCE <password> <url>"
                        return self._parse_source_url_format(mountpoint_or_url, password)
                    else:
                        # NTRIP 0.9/1.0 формат: "SOURCE <password> /<mountpoint>" или "SOURCE <password> <mountpoint>"
                        # Унифицировать обработку формата точки монтирования, убедиться что начинается с /
                        if not mountpoint_or_url.startswith('/'):
                            mountpoint = '/' + mountpoint_or_url
                        else:
                            mountpoint = mountpoint_or_url
                        
                        self.ntrip1_password = password
                        return 'SOURCE', mountpoint, 'NTRIP/1.0'
            else:
                raise ValueError(f"Invalid SOURCE request format: {request_line}")
        
        # NTRIP 1.0 ADMIN формат: "ADMIN <password> <path>"
        elif method == 'ADMIN' and len(parts) >= 3:
            password = parts[1]
            path = parts[2]
            if not path.startswith('/'):
                path = '/' + path
            self.ntrip1_password = password
            return 'ADMIN', path, 'NTRIP/1.0'
        
        # Стандартный HTTP формат: "METHOD PATH PROTOCOL"
        elif len(parts) == 3:
            method, path, protocol = parts
            
            # Для RTSP протокола сохранить оригинальный URL формат
            if protocol.startswith('RTSP/'):
                # RTSP URL должен сохранять полный формат, не требуется добавлять префикс
                return method, path, protocol
            else:
                # Для HTTP протокола убедиться что путь начинается с /
                if not path.startswith('/'):
                    path = '/' + path
                return method, path, protocol
        
        else:
            raise ValueError(f"Invalid request line format: {request_line}")
    
    def _parse_source_url_format(self, url, password=None):
        """Распарсить URL формат в SOURCE запросе"""
        from urllib.parse import urlparse
        
        if url.startswith(('http://', 'https://')):
            parsed = urlparse(url)
            
            mountpoint = parsed.path
            if not mountpoint or mountpoint == '/':
                raise ValueError(f"Invalid mountpoint in URL: {url}")

            if not mountpoint.startswith('/'):
                mountpoint = '/' + mountpoint

            if parsed.username and parsed.password:

                self.ntrip1_password = parsed.password
            elif password:
                self.ntrip1_password = password
            
            if parsed.hostname:
                self.parsed_host = parsed.hostname
            if parsed.port:
                self.parsed_port = parsed.port
            
            return 'SOURCE', mountpoint, 'NTRIP/0.8'
        
        elif url.startswith('rtsp://'):
            
            parsed = urlparse(url)
            
            
            mountpoint = parsed.path
            if not mountpoint or mountpoint == '/':
                raise ValueError(f"Invalid mountpoint in RTSP URL: {url}")
            
            
            if not mountpoint.startswith('/'):
                mountpoint = '/' + mountpoint
            
            
            if parsed.username and parsed.password:
                self.ntrip1_password = parsed.password
            elif password:
                self.ntrip1_password = password
            
            if parsed.hostname:
                self.parsed_host = parsed.hostname
            if parsed.port:
                self.parsed_port = parsed.port
            
            return 'SOURCE', mountpoint, 'NTRIP/0.8'
        
        elif url.startswith('/'):
            
            if password:
                self.ntrip1_password = password
            return 'SOURCE', url, 'NTRIP/0.8'
        
        else:
            
            mountpoint = '/' + url if not url.startswith('/') else url
            if password:
                self.ntrip1_password = password
            return 'SOURCE', mountpoint, 'NTRIP/0.8'
    
    def _parse_headers(self, header_lines):
        """Распарсить заголовки запроса"""
        headers = {}
        for line in header_lines:
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip().lower()] = value.strip()
        return headers
    
    def _determine_ntrip_version(self, headers, request_line):
        """Определить тип NTRIP протокола"""
        
        if request_line.startswith(('SOURCE ', 'ADMIN ')):
            # Обработка SOURCE и ADMIN запросов
            parts = request_line.split()
            if len(parts) >= 2:

                second_param = parts[1] if len(parts) == 2 else parts[2] if len(parts) >= 3 else ""
                if (second_param.startswith(('http://', 'https://', 'rtsp://')) or 
                    (len(parts) == 2 and (second_param.startswith('/') or not second_param.startswith('http')))):
                    self.ntrip_version = "0.8"
                    self.protocol_type = "ntrip0_8"
                    
                    message_key = f"ntrip_08_request_{self.client_address[0]}"
                    if anti_spam_logger.should_log(message_key):
                        suppressed = anti_spam_logger.get_suppressed_count(message_key)
                        if suppressed > 0:
                            logger.log_debug(f"Обнаружен NTRIP 0.8 запрос: {request_line.split()[0]} - {self.client_address} (подавлено {suppressed} похожих сообщений)", 'ntrip')
                        else:
                            logger.log_debug(f"Обнаружен NTRIP 0.8 запрос: {request_line.split()[0]} - {self.client_address}", 'ntrip')
                    return
            
            # Определить как NTRIP 1.0
            self.ntrip_version = "1.0"
            self.protocol_type = "ntrip1_0"
            
            message_key = f"ntrip_10_request_{self.client_address[0]}"
            if anti_spam_logger.should_log(message_key):
                suppressed = anti_spam_logger.get_suppressed_count(message_key)
                if suppressed > 0:
                    logger.log_debug(f"Обнаружен NTRIP 1.0 запрос: {request_line.split()[0]} - {self.client_address} (подавлено {suppressed} похожих сообщений)", 'ntrip')
                else:
                    logger.log_debug(f"Обнаружен NTRIP 1.0 запрос: {request_line.split()[0]} - {self.client_address}", 'ntrip')
            return
        
        
        # Определить тип протокола из строки запроса
        if 'HTTP/' in request_line:
            protocol_type = "http"
        elif 'RTSP/' in request_line:
            protocol_type = "rtsp"
            self.ntrip_version = "1.0"
            self.protocol_type = "rtsp"
            logger.log_debug(f"Обнаружен RTSP протокол: {self.client_address}", 'ntrip')
            return
        else:
            protocol_type = "unknown"
        
        # Обработка HTTP запросов (POST, GET)
        if request_line.startswith(('POST ', 'GET ')) and 'HTTP/' in request_line:
            user_agent = headers.get('user-agent', '').lower()
            
            # Проверить User-Agent на наличие NTRIP клиентов
            if any(ntrip_ua in user_agent for ntrip_ua in ['ntrip', 'rtk', 'gnss', 'gps']):
                # Определить версию по User-Agent или версии HTTP
                if '2.0' in user_agent or 'HTTP/1.1' in request_line:
                    self.ntrip_version = "2.0"
                    self.protocol_type = "ntrip2_0"
                    logger.log_debug(f"Обнаружен NTRIP 2.0 HTTP формат: {self.client_address}", 'ntrip')
                else:
                    self.ntrip_version = "1.0"
                    self.protocol_type = "ntrip1_0_http"
                    log_debug(f"Обнаружен NTRIP 1.0 HTTP формат: {self.client_address}")
                return
            
            # Проверить наличие Authorization заголовка (возможно NTRIP клиент)
            if 'authorization' in headers:
                
                if 'HTTP/1.1' in request_line:
                    self.ntrip_version = "2.0"
                    self.protocol_type = "ntrip2_0"
                    log_debug(f"Обнаружен NTRIP 2.0 HTTP формат аутентификации: {self.client_address}")
                else:
                    self.ntrip_version = "1.0"
                    self.protocol_type = "ntrip1_0_http"
                    log_debug(f"Обнаружен NTRIP 1.0 HTTP формат аутентификации: {self.client_address}")
                return
            
            # Извлекаем path из request_line для проверки
            try:
                request_parts = request_line.split()
                if len(request_parts) >= 2:
                    request_path = request_parts[1]
                    if protocol_type == "http" and "ntrip" in user_agent and request_path not in ["/", ""]:
                        self.ntrip_version = "2.0"
                        self.protocol_type = "ntrip2_0"
                        log_debug(f"NTRIP 2.0 определен по пути: {self.client_address}")
                        return
            except Exception:
                pass  # Игнорируем ошибки парсинга в этом месте
        
        # Проверить заголовок Ntrip-Version (специфичен для NTRIP 2.0)
        ntrip_version = headers.get('ntrip-version', '')
        if 'NTRIP/2.0' in ntrip_version:
            self.ntrip_version = "2.0"
            self.protocol_type = "ntrip2_0"
            log_debug(f"Обнаружен NTRIP 2.0 протокол: {self.client_address}")
        elif protocol_type == "http":
            # HTTP запрос без заголовка Ntrip-Version, определить нужно ли понижение версии протокола
            if self._should_downgrade_protocol(headers):
                self.ntrip_version = "1.0"
                self.protocol_type = "ntrip1_0"
                log_debug(f"Протокол понижен до NTRIP 1.0: {self.client_address}")
            else:
                # Попытка определить по User-Agent
                user_agent = headers.get('user-agent', '').lower()
                if any(keyword in user_agent for keyword in ['ntrip', 'rtk', 'gnss']):
                    self.ntrip_version = "2.0"
                    self.protocol_type = "ntrip2_0"
                    log_debug(f"Определен NTRIP 2.0 по User-Agent: {self.client_address}")
                else:
                    self.ntrip_version = "2.0"
                    self.protocol_type = "http"
                    log_debug(f"Использовать HTTP протокол: {self.client_address}")
        else:
            # В остальных случаях по умолчанию NTRIP 1.0
            self.ntrip_version = "1.0"
            self.protocol_type = "ntrip1_0"
            log_debug(f"По умолчанию используется NTRIP 1.0: {self.client_address}")
    
    def _should_downgrade_protocol(self, headers):
        """Определить, следует ли понизить версию протокола до NTRIP 1.0"""
        
        user_agent = headers.get('user-agent', '').lower()
        old_clients = ['ntrip', 'rtk', 'gnss', 'leica', 'trimble']
        
        for client in old_clients:
            if client in user_agent and '2.0' not in user_agent:
                return True
        
        required_headers = ['connection', 'host']
        missing_headers = [h for h in required_headers if h not in headers]
        
        return len(missing_headers) > 0
    
    def _is_valid_request(self, method, path, headers):
        """Проверить валидность запроса"""
        
        if not method:
            return False, "Missing request method"
        if not path:
            return False, "Invalid path format"
        
        if hasattr(self, 'protocol_type') and self.protocol_type == 'rtsp':
            # Проверка формата RTSP пути
            if not (path.startswith('/') or path.startswith('rtsp://')):
                return False, "Invalid RTSP path format"
        else:
            # Проверка формата обычного пути
            if not path.startswith('/'):
                return False, "Invalid path format"
        

        # Для всех HTTP-подобных протоколов автоматически добавляем Host, если он отсутствует
        # Это позволяет работать с устройствами, которые не отправляют Host заголовок
        if self.protocol_type in ['http', 'ntrip2_0', 'ntrip1_0_http']:
            if 'host' not in headers:
                # Используем IP адрес клиента и порт сервера для формирования Host
                # Это стандартная практика когда Host заголовок отсутствует
                try:
                    # Получаем порт сервера из сокета
                    server_port = self.client_socket.getsockname()[1]
                    # Используем IP адрес клиента (который использовался для подключения)
                    # и порт сервера
                    host_value = f"{self.client_address[0]}:{server_port}"
                    headers['host'] = host_value
                    log_debug(f"Автоматически добавлен Host заголовок для {self.protocol_type}: {host_value} (клиент: {self.client_address})")
                except Exception as e:
                    # Если не удалось получить порт, используем дефолтное значение из конфигурации
                    host_value = f"{self.client_address[0]}:{config.NTRIP_PORT}"
                    headers['host'] = host_value
                    log_debug(f"Использовано значение Host по умолчанию: {host_value} (клиент: {self.client_address}, ошибка: {e})")
        
        supported_methods = ['GET', 'POST', 'SOURCE', 'ADMIN', 'OPTIONS']
        
        if hasattr(self, 'protocol_type') and self.protocol_type == 'rtsp':
            rtsp_methods = ['DESCRIBE', 'SETUP', 'PLAY', 'PAUSE', 'TEARDOWN', 'RECORD']
            supported_methods.extend(rtsp_methods)
        
        if method.upper() not in supported_methods:
            return False, f"Unsupported method: {method}"
        
        return True, "Valid request"
    
    def _is_empty_request(self, method, path, headers):
        """Проверить, является ли запрос пустым"""
        return not method and not path and not headers
    
    def _sanitize_request_for_logging(self, request_data):
        """Отфильтровать чувствительную информацию из данных запроса"""
        try:
            
            lines = request_data.replace('\r\n', '\n').replace('\r', '\n').split('\n')
            sanitized_lines = []

            if lines:
                first_line = lines[0].strip()
                # Проверить, является ли это NTRIP 1.0 форматом (SOURCE password mount или GET mount password)
                if (first_line.startswith('SOURCE ') and len(first_line.split()) >= 3) or \
                   (first_line.startswith('GET ') and len(first_line.split()) >= 3):
                    parts = first_line.split()
                    if len(parts) >= 3:
                        method = parts[0]
                        if method == 'SOURCE':
                            
                            mount = parts[2]
                            
                            if len(parts) > 3:
                                additional_info = ' '.join(parts[3:])
                                sanitized_lines.append(f'{method} [PASSWORD_REDACTED] {mount} {additional_info}')
                            else:
                                sanitized_lines.append(f'{method} [PASSWORD_REDACTED] {mount}')
                        elif method == 'GET':
                            
                            mount = parts[1]   
                            sanitized_lines.append(f'{method} {mount} [PASSWORD_REDACTED]')
                    else:
                        sanitized_lines.append(first_line)
                else:
                    
                    sanitized_lines.append(first_line)
            
            for line in lines[1:]:
                line_lower = line.lower()
                
                if 'authorization:' in line_lower:
                    
                    if 'basic' in line_lower:
                        sanitized_lines.append('Authorization: Basic [REDACTED]')
                    elif 'digest' in line_lower:
                        sanitized_lines.append('Authorization: Digest [REDACTED]')
                    else:
                        sanitized_lines.append('Authorization: [REDACTED]')
                else:
                    sanitized_lines.append(line)
            
            return '\n'.join(sanitized_lines).replace('\r', '').strip()
        except Exception:
            
            return '[REQUEST DATA - SANITIZATION FAILED]'
    
    def verify_user(self, mount, auth_header, request_type="upload"):
        """Проверить валидность пользователя и точки монтирования в NTRIP запросе
        """
        try:
            # Унифицировать обработку имени точки монтирования, убедиться что удален ведущий /
            mount_name = mount.lstrip('/')
            self.mount = mount_name
            
            if self.protocol_type == "ntrip1_0":
                
                if auth_header.startswith('Basic '):
                    return self._verify_basic_auth(mount, auth_header, request_type)
                elif auth_header.startswith('Digest '):
                    return self._verify_digest_auth(mount, auth_header, request_type)
                elif hasattr(self, 'ntrip1_password') and self.ntrip1_password:
                   
                    mount_password = self.ntrip1_password
                    

                    is_valid, error_msg = self.db_manager.verify_mount_and_user(mount_name, username=None, password=None, mount_password=mount_password)
                    
                    if not is_valid:
                        return False, error_msg
                    
                    self.username = f"source_{mount_name}"
                    
                    return True, "Authentication successful"
                else:
                    
                    return False, "Authentication required"
            
            elif self.protocol_type == "ntrip1_0_http":
                 if auth_header.startswith('Basic '):
                     return self._verify_basic_auth(mount, auth_header, request_type)
                 elif auth_header.startswith('Digest '):
                     return self._verify_digest_auth(mount, auth_header, request_type)
                 else:
                     
                     if hasattr(self, 'ntrip1_password') and self.ntrip1_password:
                         password = self.ntrip1_password
                         
                         is_valid, error_msg = self.db_manager.verify_mount_and_user(mount_name, username=None, password=None, mount_password=password, protocol_version="1.0")
                         if not is_valid:
                             return False, error_msg
                         
                         self.username = f"http_{mount_name}"
                         
                         return True, "Authentication successful"
                     return False, "Missing authorization"
            
            # NTRIP 0.8 URL формат аутентификации (пароль обязателен)
            elif self.protocol_type == "ntrip0_8":
                 
                 if hasattr(self, 'ntrip1_password') and self.ntrip1_password:
                     password = self.ntrip1_password
                     
                     # Для NTRIP 0.8 формата проверять только точку монтирования и пароль, не проверять пользователя
                     is_valid, error_msg = self.db_manager.verify_mount_and_user(mount_name, username=None, password=None, mount_password=password, protocol_version="1.0")
                     
                     if not is_valid:
                         return False, error_msg
                     
                     self.username = f"ntrip08_{mount_name}"
                     
                     return True, "Authentication successful"
                 else:
                     
                     return False, "Authentication required"
            
            elif self.protocol_type == "ntrip2_0":
                 if auth_header.startswith('Basic '):
                     return self._verify_basic_auth(mount, auth_header, request_type)
                 elif auth_header.startswith('Digest '):
                     return self._verify_digest_auth(mount, auth_header, request_type)
                 elif not auth_header and hasattr(self, 'ntrip1_password') and self.ntrip1_password:
                   
                     password = self.ntrip1_password
                     
                     
                     is_valid, error_msg = self.db_manager.verify_mount_and_user(mount_name, username=None, password=None, mount_password=password, protocol_version="1.0")
                     if not is_valid:
                         return False, error_msg
                     
                     self.username = f"ntrip20_{mount_name}"
                     
                     return True, "Authentication successful"
                 else:
                     return False, "Invalid authorization format"
            
            elif self.protocol_type == "rtsp":
                 if auth_header.startswith('Basic '):
                     return self._verify_basic_auth(mount, auth_header, request_type)
                 elif auth_header.startswith('Digest '):
                     return self._verify_digest_auth(mount, auth_header, request_type)
                 elif not auth_header and hasattr(self, 'ntrip1_password') and self.ntrip1_password:

                     password = self.ntrip1_password
                     
                     is_valid, error_msg = self.db_manager.verify_mount_and_user(mount_name, username=None, password=None, mount_password=password, protocol_version="1.0")
                     if not is_valid:
                         return False, error_msg
                     
                     self.username = f"rtsp_{mount_name}"
                     
                     return True, "Authentication successful"
                 else:
                     return False, "Invalid authorization format"
            
            else:
                 if not auth_header:
                     return False, "Missing authorization"

                 if not auth_header.startswith('Basic '):
                     return False, "Invalid authorization format"
                 
                 encoded_credentials = auth_header[6:]
                 decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
                 
                 if ':' not in decoded_credentials:
                     return False, "Invalid credentials format"
                 
                 username, password = decoded_credentials.split(':', 1)
                 self.username = username
                 
                 # Проверить точку монтирования и пользователя (по умолчанию используется протокол 1.0)
                 is_valid, error_msg = self.db_manager.verify_mount_and_user(mount_name, username, password, mount_password=password, protocol_version="1.0")
                 
                 if not is_valid:
                     return False, error_msg
                 
                 # Проверить ограничение количества подключений пользователя
                 current_connections = connection.get_user_connection_count(username)
                 if current_connections >= MAX_CONNECTIONS_PER_USER:
                     return False, f"User connection limit exceeded (max: {MAX_CONNECTIONS_PER_USER})"
                 
                 return True, "Authentication successful"
        
        except Exception as e:
            logger.log_error(f"Исключение при проверке пользователя: {e}", exc_info=True)
            return False, "Authentication error"
    
    def _verify_basic_auth(self, mount, auth_header, request_type="upload"):
        """Проверить Basic аутентификацию"""
        try:
            # Унифицировать обработку имени точки монтирования
            mount_name = mount.lstrip('/')
            
            encoded_credentials = auth_header[6:]
            

            try:
                decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
            except (ValueError, UnicodeDecodeError) as e:
                logger.log_debug(f"Не удалось декодировать Basic аутентификацию {self.client_address}: {e}", 'ntrip')
                return False, "Invalid credentials format"
            
            if ':' not in decoded_credentials:
                return False, "Invalid credentials format"
            
            username, password = decoded_credentials.split(':', 1)
            self.username = username

            if request_type == "download":
                
                is_valid, error_msg = self.db_manager.verify_download_user(mount_name, username, password)
            else:
                
                if self.protocol_type == "ntrip2_0":
                    
                    is_valid, error_msg = self.db_manager.verify_mount_and_user(mount_name, username, password, mount_password=None, protocol_version="2.0")
                else:
                    
                    is_valid, error_msg = self.db_manager.verify_mount_and_user(mount_name, username, password, mount_password=password, protocol_version="1.0")
            
            if not is_valid:
                return False, error_msg
            

            current_connections = connection.get_user_connection_count(username)
            if current_connections >= MAX_CONNECTIONS_PER_USER:
                return False, f"User connection limit exceeded (max: {MAX_CONNECTIONS_PER_USER})"
            
            return True, "Authentication successful"
        except Exception as e:
            logger.log_error(f"Исключение при Basic аутентификации: {e}", exc_info=True)
            return False, "Authentication error"
    
    def _verify_digest_auth(self, mount, auth_header, request_type="upload"):
        """Проверить Digest аутентификацию"""
        try:
            
            mount_name = mount.lstrip('/')
            
            digest_params = self._parse_digest_auth(auth_header)
            
            if not digest_params:
                return False, "Invalid digest format"
            
            username = digest_params.get('username')
            if not username:
                return False, "Missing username in digest"
            
            self.username = username
            
            stored_password = self.db_manager.get_user_password(username)
            if not stored_password:
                return False, "Invalid credentials"

            if not self._validate_digest_response(digest_params, stored_password, mount_name):
                return False, "Invalid digest response"

            if request_type == "download":
               
                is_valid, error_msg = self.db_manager.verify_download_user(mount_name, username, stored_password)
            else:
                
                if self.protocol_type == "ntrip2_0":
                    
                    is_valid, error_msg = self.db_manager.verify_mount_and_user(mount_name, username, stored_password, mount_password=None, protocol_version="2.0")
                else:
                    
                    is_valid, error_msg = self.db_manager.verify_mount_and_user(mount_name, username, stored_password, mount_password=stored_password, protocol_version="1.0")
            
            if not is_valid:
                return False, error_msg
            
            current_connections = connection.get_user_connection_count(username)
            if current_connections >= MAX_CONNECTIONS_PER_USER:
                return False, f"User connection limit exceeded (max: {MAX_CONNECTIONS_PER_USER})"
            
            return True, "Authentication successful"
        except Exception as e:
            logger.log_error(f"Исключение при Digest аутентификации: {e}", exc_info=True)
            return False, "Authentication error"
    
    def _parse_digest_auth(self, auth_header):
        """Распарсить заголовок Digest аутентификации"""
        import re
        
        digest_pattern = r'(\w+)=(?:"([^"]*)"|([^,\s]*))'  
        matches = re.findall(digest_pattern, auth_header[7:])
        
        params = {}
        for match in matches:
            key = match[0]
            value = match[1] if match[1] else match[2]
            params[key] = value
        
        return params
    
    def _validate_digest_response(self, params, password, uri):
        """Проверить Digest ответ"""
        import hashlib
        
        try:
            username = params.get('username')
            realm = params.get('realm')
            nonce = params.get('nonce')
            response = params.get('response')
            method = getattr(self, 'current_method', 'GET')
            
            if not all([username, realm, nonce, response]):
                return False
            
            # HA1
            ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
            
            # HA2
            ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
            
            
            expected_response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
            
            return response.lower() == expected_response.lower()
        except Exception:
            return False
    

    
    def handle_options(self, headers):
        """Обработать OPTIONS запрос (CORS предпроверка и т.д.)"""
        try:
            logger.log_debug(f"OPTIONS запрос {self.client_address}")
            
            # CORS заголовки ответа - удалены, NTRIP протокол не требует CORS
            # NTRIP клиенты не являются браузерами, не подвержены ограничениям CORS
            
            # Использовать стандартный метод ответа, убедиться что включен Content-Length
            self._send_response(
                "HTTP/1.1 200 OK",
                content_type="text/plain",
                content=""
            )
            
            logger.log_debug(f"OPTIONS запрос обработан {self.client_address}")
            
        except Exception as e:
            logger.log_error(f"Исключение при обработке OPTIONS запроса {self.client_address}: {e}", exc_info=True)
            self.send_error_response(500, "Internal Server Error")
    
    def handle_rtsp_command(self, method, path, headers):
        """Обработать RTSP команду протокола"""
        try:
            # Извлечь имя точки монтирования
            if path.startswith('rtsp://'):
                # Извлечь точку монтирования из RTSP URL
                from urllib.parse import urlparse
                parsed = urlparse(path)
                mount = parsed.path.lstrip('/')
            else:
                mount = path.lstrip('/')
            
            if not mount:
                self.send_error_response(400, "Missing mount point")
                return
            
            self.mount = mount
            
            # Проверить пользователя (RTSP может использовать другой механизм аутентификации)
            auth_header = headers.get('authorization', '')
            is_valid, message = self.verify_user(mount, auth_header)
            
            if not is_valid:
                self.send_auth_challenge(message)
                return
            
            # Обработать в зависимости от типа RTSP команды
            if method.upper() == 'DESCRIBE':
                self._handle_rtsp_describe(mount, headers)
            elif method.upper() == 'SETUP':
                self._handle_rtsp_setup(mount, headers)
            elif method.upper() == 'PLAY':
                self._handle_rtsp_play(mount, headers)
            elif method.upper() == 'PAUSE':
                self._handle_rtsp_pause(mount, headers)
            elif method.upper() == 'TEARDOWN':
                self._handle_rtsp_teardown(mount, headers)
            elif method.upper() == 'RECORD':
                self._handle_rtsp_record(mount, headers)
            else:
                self.send_error_response(501, f"RTSP method not implemented: {method}")
                
        except Exception as e:
            logger.log_error(f"Исключение при обработке RTSP команды: {e}", exc_info=True)
            self.send_error_response(500, "Internal Server Error")
    
    def _handle_rtsp_describe(self, mount, headers):
        """Обработать RTSP DESCRIBE команду"""
        # Проверить существует ли точка монтирования
        if not connection.check_mount_exists(mount):
            self.send_error_response(404, "Mount point not found")
            return
        
        # Сгенерировать SDP описание
        sdp_content = self._generate_sdp_description(mount)
        
        rtsp_headers = {
            'Content-Type': 'application/sdp',
            'Content-Length': str(len(sdp_content))
        }
        
        self._send_response('RTSP/1.0 200 OK', content_type='application/sdp', 
                          content=sdp_content, additional_headers=rtsp_headers)
    
    def _handle_rtsp_setup(self, mount, headers):
        """Обработать RTSP SETUP команду"""
        # Проверить существует ли точка монтирования
        if not connection.check_mount_exists(mount):
            cseq = headers.get('cseq', '1')
            response_headers = {'CSeq': cseq}
            self._send_response("RTSP/1.0 404 Not Found", additional_headers=response_headers)
            return
        
        # Распарсить Transport заголовок
        transport = headers.get('transport', 'RTP/AVP;unicast')
        client_port = '8000-8001'  # Порт по умолчанию
        
        # Извлечь информацию о порте клиента
        if 'client_port=' in transport:
            try:
                client_port = transport.split('client_port=')[1].split(';')[0]
            except:
                pass
        
        session_id = f"{mount}-{int(time.time())}"
        
        cseq = headers.get('cseq', '1')
        rtsp_headers = {
            'CSeq': cseq,
            'Transport': f'RTP/AVP;unicast;client_port={client_port};server_port=8002-8003',
            'Session': session_id,
            'Cache-Control': 'no-cache'
        }
        
        self._send_response('RTSP/1.0 200 OK', additional_headers=rtsp_headers)
    
    def _handle_rtsp_play(self, mount, headers):
        """Обработать RTSP PLAY команду"""
        cseq = headers.get('cseq', '1')
        session = headers.get('session', '')
        
        rtsp_headers = {
            'CSeq': cseq,
            'Session': session,
            'Range': 'npt=0.000-',
            'RTP-Info': f'url=rtsp://{config.HOST if config.HOST != "0.0.0.0" else "localhost"}:{config.NTRIP_PORT}/{mount};seq=1;rtptime=0'
        }
        
        self._send_response('RTSP/1.0 200 OK', additional_headers=rtsp_headers)
        # Начать передачу потока данных
        self.handle_download('/' + mount, headers)
    
    def _handle_rtsp_pause(self, mount, headers):
        """Обработать RTSP PAUSE команду"""
        cseq = headers.get('cseq', '1')
        session = headers.get('session', '')
        
        rtsp_headers = {
            'CSeq': cseq,
            'Session': session
        }
        
        self._send_response('RTSP/1.0 200 OK', additional_headers=rtsp_headers)
    
    def _handle_rtsp_teardown(self, mount, headers):
        """Обработать RTSP TEARDOWN команду"""
        cseq = headers.get('cseq', '1')
        session = headers.get('session', '')
        
        rtsp_headers = {
            'CSeq': cseq,
            'Session': session
        }
        
        self._send_response('RTSP/1.0 200 OK', additional_headers=rtsp_headers)
        # Очистить подключение
        self._cleanup()
    
    def _handle_rtsp_record(self, mount, headers):
        """Обработать RTSP RECORD команду"""
        cseq = headers.get('cseq', '1')
        session = headers.get('session', '')
        
        rtsp_headers = {
            'CSeq': cseq,
            'Session': session
        }
        
        self._send_response('RTSP/1.0 200 OK', additional_headers=rtsp_headers)
        
        self.handle_upload('/' + mount, headers)
    
    def _generate_sdp_description(self, mount):
        """Сгенерировать SDP описание"""
        # Получить реальный IP адрес для SDP описания
        origin_ip = config.HOST if config.HOST != "0.0.0.0" else "127.0.0.1"
        sdp = f"""v=0
o=- 0 0 IN IP4 {origin_ip}
s=NTRIP Stream {mount}
c=IN IP4 0.0.0.0
t=0 0
m=application 0 RTP/AVP 96
a=rtpmap:96 rtcm/1000
a=control:*
"""
        return sdp
    
    def handle_upload(self, path, headers):
        """Обработать запрос на загрузку"""
        try:
            # Использовать механизм защиты от спама для логирования HANDLE_UPLOAD
            message_key = f"handle_upload_{self.client_address[0]}_{path}"
            if anti_spam_logger.should_log(message_key):
                suppressed = anti_spam_logger.get_suppressed_count(message_key)
                if suppressed > 0:
                    logger.log_info(f"HANDLE_UPLOAD вызван {self.client_address}: path={path} (подавлено {suppressed} похожих сообщений)")
                else:
                    logger.log_info(f"HANDLE_UPLOAD вызван {self.client_address}: path={path}")
            logger.log_debug(f"handle_upload начал обработку {self.client_address}: path={path}")
            
            # Вывести текущее состояние подключения
            # print(f"\n>>> Новый запрос на загрузку - IP: {self.client_address[0]}, точка монтирования: {path.lstrip('/')}, время: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
            # print(f">>> Детали запроса - метод: POST, путь: {path}, пользовательский агент: {headers.get('User-Agent', 'Unknown')}")
            
            connection.get_connection_manager().cleanup_zombie_connections()
            connection.get_connection_manager().force_refresh_connections()
            
            # Извлечь имя точки монтирования
            mount = path.lstrip('/')
            if not mount:
                self.send_error_response(400, "Missing mount point")
                return
            
            self.mount = mount
             
            if connection.get_connection_manager().is_mount_online(mount):
                existing_mount = connection.get_connection_manager().get_mount_info(mount)
                if existing_mount and existing_mount['ip_address'] != self.client_address[0]:
                    
                    message_key = f"mount_occupied_{mount}_{existing_mount['ip_address']}"
                    if anti_spam_logger.should_log(message_key):
                        suppressed = anti_spam_logger.get_suppressed_count(message_key)
                        if suppressed > 0:
                            logger.log_warning(f"Точка монтирования {mount} уже занята {existing_mount['ip_address']}, отклонено подключение от {self.client_address[0]} (подавлено {suppressed} похожих сообщений)")
                        else:
                            logger.log_warning(f"Точка монтирования {mount} уже занята {existing_mount['ip_address']}, отклонено подключение от {self.client_address[0]}")
                    self.send_error_response(409, f"Mount point {mount} is already online from {existing_mount['ip_address']}")
                    
                    try:
                        self.client_socket.close()
                    except:
                        pass
                    return
                elif existing_mount and existing_mount['ip_address'] == self.client_address[0]:
                    logger.log_warning(f"Обнаружено повторное подключение с того же IP({self.client_address[0]}), возможно соединение было разорвано, разрешаем переподключение")
                    
                    connection.get_connection_manager().remove_mount_connection(mount, "Повторное подключение с того же IP")
            
            # Все запросы должны пройти полную проверку в базе данных, убедиться что точка монтирования существует и пароль правильный
            auth_header = headers.get('authorization', '')
            logger.log_info(f"handle_upload начал проверку {self.client_address}: mount={mount}, auth_header={auth_header[:50] if auth_header else 'None'}")
            is_valid, message = self.verify_user(mount, auth_header)
            
            logger.log_info(f"handle_upload результат проверки {self.client_address}: is_valid={is_valid}, message={message}")
            
            if not is_valid:
                logger.log_warning(f"handle_upload аутентификация не прошла {self.client_address}: {message}")
                self.send_auth_challenge(message)
                # При неудачной аутентификации сразу закрыть сокет
                try:
                    self.client_socket.close()
                except:
                    pass
                return
             
            try:
                success, message = connection.get_connection_manager().add_mount_connection(mount, self.client_address[0], getattr(self, 'user_agent', 'Unknown'), getattr(self, 'ntrip_version', '1.0'), self.client_socket)
                if not success:
                    logger.log_warning(f"Подключение к точке монтирования {mount} отклонено: {message}")
                    logger.log_info(f"Детали отклонения подключения - точка монтирования: {mount}, IP: {self.client_address[0]}, причина: {message}")
                    self.send_error_response(409, message)
                    
                    try:
                        self.client_socket.close()
                    except:
                        pass
                    return

                self.mount_connection_established = True
                
                if success:
                    logger.log_info(f"Точка монтирования {mount} успешно добавлена в менеджер подключений: {message}")
                else:
                    logger.log_warning(f"Не удалось добавить точку монтирования {mount} в менеджер подключений: {message}")
            except Exception as e:
                logger.log_error(f"Исключение при добавлении точки монтирования {mount} в менеджер подключений: {e}", exc_info=True)

            self.send_upload_success_response()
            
            username_for_log = getattr(self, 'username', mount) if hasattr(self, 'username') else mount
            logger.log_mount_operation('upload_connected', mount, username_for_log)
            
            logger.log_info(f"=== Начало приема RTCM данных ===: mount={mount}")
            self._receive_rtcm_data(mount)
        
        except Exception as e:
            logger.log_error(f"Исключение при обработке запроса на загрузку: {e}", exc_info=True)
            self.send_error_response(500, "Internal Server Error")
    
    def handle_download(self, path, headers):
        """Обработать запрос на скачивание"""
        try:
            
            if path.strip().lower() in ['/', '', '/sourcetable']:
                self._send_mount_list()
                return
            
            mount = path.lstrip('/')
            self.mount = mount

            auth_header = next((v for k, v in headers.items() if k.lower() == 'authorization'), '')
            is_valid, message = self.verify_user(mount, auth_header, "download")
            
            if not is_valid:
                self.send_auth_challenge(message)
                return
            
            if not self.db_manager.check_mount_exists_in_db(mount):
                self.send_error_response(404, "Mount point not found")
                return
            
            # Добавить в менеджер подключений
            connection_id = connection.add_user_connection(self.username, mount, self.client_address[0])
            
            # Добавить клиента в форвардер
            try:
                self.client_info = forwarder.add_client(self.client_socket, self.username, mount,
                                                       self.user_agent, self.client_address, 
                                                       self.ntrip_version, connection_id)
                if not self.client_info:
                    self.send_error_response(500, "Failed to add client")
                    return
            except Exception as e:
                logger.log_error(f"Не удалось добавить клиента: {e}", exc_info=True)
                self.send_error_response(500, "Failed to add client")
                return
            
            self.send_download_success_response()
            
            logger.log_client_connect(self.username, mount, self.client_address[0], self.user_agent)
            
            self._keep_connection_alive()
        
        except Exception as e:
            logger.log_error(f"Исключение при обработке запроса на скачивание: {e}", exc_info=True)
            self.send_error_response(500, "Internal Server Error")
    
    def handle_http_get(self, path, headers):
        """Обработать обычный HTTP GET запрос"""
        try:
            if path == '/' or path == '':
                content = "<!DOCTYPE html><html><head><title>NTRIP Caster</title></head><body><h1>NTRIP Caster Server</h1><p>This is an NTRIP Caster server.</p></body></html>"
                self._send_response(
                    "HTTP/1.1 200 OK",
                    content_type="text/html",
                    content=content
                )
            else:
                self.send_error_response(404, "Not Found")
        except Exception as e:
            logger.log_error(f"Исключение при обработке HTTP GET запроса: {e}", exc_info=True)
            self.send_error_response(500, "Internal Server Error")
    
    def _receive_rtcm_data(self, mount):
        """Цикл приема RTCM данных"""
        try:
            while True:
                try:
                    data = self.client_socket.recv(BUFFER_SIZE)
                    if not data:
                        # Подключение закрыто
                        logger.log_debug(f"Подключение к точке монтирования {mount} закрыто", 'ntrip')
                        break
                    
                    forwarder.upload_data(mount, data)

                    connection.get_connection_manager().update_mount_data_stats(mount, len(data))
                    
                except OSError as e:
                    
                    if e.winerror == 10038:  #10038 
                        logger.log_debug(f"Сокет точки монтирования {mount} закрыт, прекращаем прием данных", 'ntrip')
                    else:
                        logger.log_error(f"Ошибка сокета точки монтирования {mount}: {e}", 'ntrip')
                    break
                except socket.timeout:
                    logger.log_debug(f"Таймаут приема данных точки монтирования {mount}", 'ntrip')
                    continue
        
        except Exception as e:
            logger.log_error(f"Исключение при приеме RTCM данных: {e}", exc_info=True)
        finally:
            
            def delayed_cleanup():
                """Функция отложенной очистки"""
                try:
                    forwarder.remove_mount_buffer(mount)
                except Exception as e:
                    logger.log_warning(f"Не удалось очистить буфер форвардера: {e}", 'ntrip')
                
                try:
                    connection.get_connection_manager().remove_mount_connection(mount)
                except Exception as e:
                    log_warning(f"Не удалось очистить подключение точки монтирования: {e}")
                

                logger.log_mount_operation('disconnected', mount)
                # Изменено на уровень debug, чтобы избежать частых логов
                log_debug(f"Отложенная очистка точки монтирования {mount} завершена")
            
            # Записать событие разрыва, изменено на уровень warning чтобы важная информация была записана
            log_warning(f"Подключение точки монтирования {mount} разорвано, очистка данных через 1.5 секунд")
            

            cleanup_timer = threading.Timer(1.5, delayed_cleanup)
            cleanup_timer.daemon = True  # Установить как демон-поток
            cleanup_timer.start()
            

            self._cleanup()
    
    def _keep_connection_alive(self):
        """Поддерживать активное подключение для скачивания"""
        try:
            
            while True:
                time.sleep(5)  
                
                if hasattr(self, 'client_info') and self.client_info:
                    
                    try:
                        
                        self.client_socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                    except (OSError, AttributeError):
                        break
                else:
                    break
        except:
            
            pass
        finally:
            
            if hasattr(self, 'client_info') and self.client_info:
                forwarder.remove_client(self.client_info)
                logger.log_client_disconnect(self.username, self.mount, self.client_address[0])
    
    def _send_mount_list(self):
        """Отправить список точек монтирования"""
        try:
            from . import config
            from datetime import datetime
            
            mount_list = connection.generate_mount_list()
            logger.log_debug(f"Сгенерирован список точек монтирования: {mount_list}", 'ntrip')
            
            
            content_lines = []
            
            # Добавить CAS информацию (информация о Caster)
            # Переиспользовать существующую конфигурацию: server_name=author, server_port=NTRIP_PORT, operator=APP_NAME, network_name=author, website_url=APP_WEBSITE, fallback_ip=HOST
            cas_line = f"CAS;{config.APP_AUTHOR};{config.NTRIP_PORT};{config.APP_NAME};{config.APP_AUTHOR};0;{config.CASTER_COUNTRY};{config.CASTER_LATITUDE};{config.CASTER_LONGITUDE};{config.HOST};0;{config.APP_WEBSITE}"
            content_lines.append(cas_line)
            
            # Добавить NET информацию (информация о сети)
            net_line = f"NET;{config.APP_AUTHOR};{config.APP_AUTHOR};B;{config.CASTER_COUNTRY};{config.APP_WEBSITE};{config.APP_WEBSITE};{config.APP_CONTACT};none"
            content_lines.append(net_line)
            
            # Добавить данные STR таблицы
            content_lines.extend(mount_list)
            
            # Преобразовать содержимое в строку
            content_str = '\r\n'.join(content_lines) + '\r\n' if content_lines else '\r\n'
            log_debug(f"Длина содержимого списка точек монтирования: {len(content_str)}")
            
            if self.ntrip_version == "2.0":
                # NTRIP 2.0 формат - использовать стандартный HTTP ответ
                current_time = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
                
                # Построить HTTP заголовки ответа
                response_lines = [
                    "HTTP/1.1 200 OK",
                    f"Server: NTRIP 2RTK caster {config.APP_VERSION}",
                    f"Date: {current_time}",
                    "Ntrip-Version: Ntrip/2.0",
                    f"Content-Length: {len(content_str.encode('utf-8'))}",
                    "Content-Type: text/plain",
                    "Connection: close",
                    "",  # Пустая строка разделяет заголовки и содержимое
                    content_str
                ]
                
                response = '\r\n'.join(response_lines)
                try:
                    self.client_socket.send(response.encode('utf-8'))
                    log_debug(f"Отправка списка точек монтирования в формате NTRIP 2.0 на {self.client_address}")
                except Exception as e:
                    logger.log_error(f"Не удалось отправить список точек монтирования NTRIP 2.0: {e}", exc_info=True)
            else:
                # NTRIP 1.0 формат - использовать формат SOURCETABLE
                current_time = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
                
                response_lines = [
                    "SOURCETABLE 200 OK",
                    f"Server: NTRIP 2RTK caster {config.APP_VERSION}",
                    f"Date: {current_time}",
                    "Ntrip-Version: Ntrip/1.0",
                    f"Content-Length: {len(content_str.encode('utf-8'))}",
                    "Content-Type: text/plain",
                    "Connection: close",
                    "",  # Пустая строка разделяет заголовки и содержимое
                    content_str,
                    "ENDSOURCETABLE"
                ]
                
                response = '\r\n'.join(response_lines)
                log_debug(f"Содержимое ответа NTRIP 1.0: {repr(response[:200])}...")
                try:
                    self.client_socket.send(response.encode('utf-8'))
                    log_debug(f"Отправка списка точек монтирования в формате NTRIP 1.0 на {self.client_address}")
                except Exception as e:
                    logger.log_error(f"Не удалось отправить список точек монтирования NTRIP 1.0: {e}", exc_info=True)
            
            log_debug(f"Отправка списка точек монтирования на {self.client_address}")
        
        except Exception as e:
            log_error(f"Исключение при отправке списка точек монтирования: {e}", exc_info=True)
    
    def send_upload_success_response(self):
        """Отправить ответ об успешной загрузке"""
        if self.ntrip_version == "2.0":
            self._send_response(
                "HTTP/1.1 200 OK",
                additional_headers=["Connection: keep-alive"]
            )
        else:
            # NTRIP 1.0 формат
            try:
                response = "ICY 200 OK\r\n\r\n"
                self.client_socket.send(response.encode('utf-8'))
            except Exception as e:
                logger.log_error(f"Не удалось отправить ответ об успешной загрузке: {e}", exc_info=True)
    
    def send_download_success_response(self):
        """Отправить ответ об успешном скачивании"""
        if self.ntrip_version == "2.0":
            # Для NTRIP 2.0 обязательно нужно добавить заголовок Ntrip-Version
            headers = ["Connection: keep-alive", "Ntrip-Version: NTRIP/2.0"]
            self._send_response(
                "HTTP/1.1 200 OK",
                content_type="application/octet-stream",
                additional_headers=headers
            )
        else:
            # NTRIP 1.0 формат - принудительно поддерживать соединение, игнорировать Connection: close от клиента
            try:
                response = "ICY 200 OK\r\nConnection: keep-alive\r\n\r\n"
                self.client_socket.send(response.encode('utf-8'))
                logger.log_debug(f"Ответ NTRIP 1.0 о скачивании отправлен, поддерживаем длительное соединение: {self.client_address}", 'ntrip')
            except Exception as e:
                logger.log_error(f"Не удалось отправить ответ об успешном скачивании: {e}", exc_info=True)
    
    def send_auth_challenge(self, message="Authentication required", auth_type="both"):
        """Отправить запрос на аутентификацию"""
        import secrets
        import time
        
        # Сгенерировать nonce для Digest аутентификации
        nonce = secrets.token_hex(16)
        realm = "NTRIP"
        
        # Построить заголовок аутентификации
        auth_headers = []
        if auth_type in ["basic", "both"]:
            auth_headers.append(f'WWW-Authenticate: Basic realm="{realm}"')
        
        if auth_type in ["digest", "both"]:
            digest_header = f'WWW-Authenticate: Digest realm="{realm}", nonce="{nonce}", algorithm=MD5, qop="auth"'
            auth_headers.append(digest_header)
        
        if self.ntrip_version == "2.0":
            self._send_response(
                "HTTP/1.1 401 Unauthorized",
                content_type="text/plain",
                content=message,
                additional_headers=auth_headers
            )
        else:
            # NTRIP 1.0 формат
            try:
                response = "SOURCETABLE 401 Unauthorized\r\n"
                for header in auth_headers:
                    response += f"{header}\r\n"
                response += "\r\n"
                self.client_socket.send(response.encode('utf-8'))
            except Exception as e:
                logger.log_error(f"Не удалось отправить запрос на аутентификацию: {e}", exc_info=True)
    
    def send_error_response(self, code, message):
        """Отправить HTTP ответ об ошибке"""
        if self.ntrip_version == "2.0":
            # Получить стандартное HTTP сообщение о статусе
            status_messages = {
                400: "Bad Request",
                401: "Unauthorized", 
                404: "Not Found",
                405: "Method Not Allowed",
                409: "Conflict",
                500: "Internal Server Error"
            }
            status_text = status_messages.get(code, "Error")
            
            self._send_response(
                f"HTTP/1.1 {code} {status_text}",
                content_type="text/plain",
                content=message
            )
        else:
            # NTRIP 1.0 формат
            try:
                response = f"ERROR {code} {message}\r\n\r\n"
                self.client_socket.send(response.encode('utf-8'))
            except Exception as e:
                logger.log_error(f"Не удалось отправить ответ об ошибке: {e}", exc_info=True)
    
    def _generate_standard_headers(self, additional_headers=None):
        """Сгенерировать стандартные HTTP заголовки ответа"""
        current_time = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        headers = []
        
        # Добавить соответствующие заголовки в зависимости от версии протокола
        if self.protocol_type == "ntrip2_0":
            # Обязательные поля заголовка для NTRIP 2.0 (см. ntrip_header_element)
            headers.append("Ntrip-Version: NTRIP/2.0")
            headers.append("Cache-Control: no-cache, no-store, must-revalidate")
            headers.append("Pragma: no-cache")
            headers.append("Expires: 0")
        elif self.protocol_type == "rtsp":
            headers.append("CSeq: 1")
            headers.append(f"Session: {id(self)}")
        elif self.ntrip_version == "2.0":
            headers.append("Ntrip-Version: NTRIP/2.0")
        
        # Общие поля заголовка
        headers.append(f"Date: {current_time}")
        headers.append(f"Server: {config.APP_NAME}/{config.VERSION}")
        
        # Заголовки, связанные с безопасностью
        headers.append("X-Content-Type-Options: nosniff")
        headers.append("X-Frame-Options: DENY")
        
        if additional_headers:
            headers.extend(additional_headers)
        
        return "\r\n".join(headers) + "\r\n"
    
    def _send_response(self, status_line, content_type=None, content=None, additional_headers=None):
        """Отправить стандартизированный HTTP ответ"""
        try:
            response = status_line + "\r\n"
            
            headers = []
            if content_type:
                headers.append(f"Content-Type: {content_type}")
            if content:
                headers.append(f"Content-Length: {len(content)}")
            
            response += self._generate_standard_headers(headers + (additional_headers or []))
            response += "\r\n"
            
            if content:
                response += content
            
            self.client_socket.send(response.encode('utf-8'))
            
        except Exception as e:
            logger.log_error(f"Не удалось отправить ответ: {e}", exc_info=True)
    
    def _cleanup(self):
        """Очистить ресурсы"""
        try:
            # print(f"\n>>> Начало очистки подключения - IP: {self.client_address[0]}, время: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")

            if hasattr(self, 'username') and hasattr(self, 'mount'):
                if hasattr(self, 'client_info'):  # Подключение для скачивания
                    # print(f">>> Удалить подключение пользователя - пользователь: {self.username}, точка монтирования: {self.mount}")
                    connection.remove_user_connection(self.username, self.client_address[0], self.mount)
                else:  # Подключение для загрузки
                    # Только действительно успешно установленные подключения точек монтирования удаляются при разрыве
                    if hasattr(self, 'mount_connection_established') and self.mount_connection_established:
                        # print(f">>> Удалить подключение точки монтирования - точка монтирования: {self.mount}")
                        connection.remove_mount_connection(self.mount)
                    else:
                        # print(f">>> Пропустить удаление подключения точки монтирования - точка монтирования: {self.mount} (подключение не было успешно установлено)")
                        pass
            else:
                # print(f">>> Пропустить удаление подключения - username существует: {hasattr(self, 'username')}, mount существует: {hasattr(self, 'mount')}") 
                pass
            
            self.client_socket.close()
            # print(f">>> Очистка подключения завершена - IP: {self.client_address[0]}")
        except Exception as e:
            logger.log_error(f"Ошибка при очистке ресурсов: {e}", exc_info=True)

class NTRIPCaster:
    """NTRIP Caster сервер - использует пул потоков для обработки множества одновременных подключений"""
    
    def __init__(self, db_manager):
        self.server_socket = None
        self.running = False
        self.db_manager = db_manager

        self.thread_pool = None
        self.connection_queue = Queue(maxsize=CONNECTION_QUEUE_SIZE)
        self.active_connections = 0
        self.connection_lock = threading.Lock()

        self.total_connections = 0
        self.rejected_connections = 0
    
    def start(self):
        """Запустить NTRIP сервер"""
        try:
            
            self._start_ntrip_server()
            
            log_system_event(f'NTRIP сервер запущен, прослушивает порт: {NTRIP_PORT}')
            
            self._main_loop()
        
        except Exception as e:
            log_error(f"Не удалось запустить NTRIP сервер: {e}", exc_info=True)
            self.stop()
    
    def _start_ntrip_server(self):
        """Запустить NTRIP сервер"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('0.0.0.0', NTRIP_PORT))
        self.server_socket.listen(MAX_CONNECTIONS)
        self.running = True
        
        self.thread_pool = ThreadPoolExecutor(
            max_workers=MAX_WORKERS,
            thread_name_prefix="NTRIP-Worker"
        )
        
        self._start_connection_handler()

        ntrip_urls = config.get_display_urls(NTRIP_PORT, "NTRIP сервер")
        if len(ntrip_urls) == 1:
            log_system_event(f'NTRIP сервер запущен, адрес прослушивания: {ntrip_urls[0]}')
        else:
            log_system_event('NTRIP сервер запущен, доступен по следующим адресам:')
            for url in ntrip_urls:
                log_system_event(f'  - {url}')
        
        log_system_event(f'Размер пула потоков: {MAX_WORKERS}, размер очереди подключений: {CONNECTION_QUEUE_SIZE}')
    

    def _main_loop(self):
        """Главный цикл, принимает клиентские подключения"""
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                
                # Проверить ограничение количества подключений
                with self.connection_lock:
                    if self.active_connections >= MAX_CONNECTIONS:
                        log_warning(f"Достигнуто максимальное количество подключений {MAX_CONNECTIONS}, отклонено подключение {client_address}")
                        client_socket.close()
                        self.rejected_connections += 1
                        continue

                try:
                    self.connection_queue.put((client_socket, client_address), timeout=1.0)
                    with self.connection_lock:
                        self.total_connections += 1
                    log_info(f"Принято подключение от {client_address}, размер очереди: {self.connection_queue.qsize()}, активных подключений: {self.active_connections}")
                except Full:
                    log_warning(f"Очередь подключений заполнена, отклонено подключение {client_address}")
                    client_socket.close()
                    self.rejected_connections += 1
            
            except socket.error as e:
                if self.running:
                    log_error(f"Исключение при принятии подключения: {e}", exc_info=True)
                break
            except Exception as e:
                log_error(f"Исключение в главном цикле: {e}", exc_info=True)
                break
    
    def _start_connection_handler(self):
        """Запустить поток обработчика подключений"""
        handler_thread = Thread(target=self._connection_handler, daemon=True)
        handler_thread.start()
        log_debug("Обработчик подключений запущен")
    
    def _connection_handler(self):
        """Обработчик подключений, извлекает подключения из очереди и передает в пул потоков"""
        while self.running:
            try:
                
                client_socket, client_address = self.connection_queue.get(timeout=1.0)
                
                future = self.thread_pool.submit(self._handle_client_connection, client_socket, client_address)

                with self.connection_lock:
                    self.active_connections += 1
                
                log_info(f"Подключение {client_address} передано в пул потоков для обработки")
                
            except Empty:
                
                continue
            except Exception as e:
                log_error(f"Исключение в обработчике подключений: {e}", exc_info=True)
    
    def _handle_client_connection(self, client_socket, client_address):
        """Обработать одно клиентское подключение"""
        try:
            
            handler = NTRIPHandler(client_socket, client_address, self.db_manager)
            handler.handle_request()
        except Exception as e:
            log_error(f"Исключение при обработке клиентского подключения {client_address}: {e}", exc_info=True)
        finally:
           
            with self.connection_lock:
                self.active_connections -= 1
            
            try:
                client_socket.close()
            except:
                pass
            
            log_info(f"Обработка клиентского подключения {client_address} завершена, активных подключений: {self.active_connections}")
    
    def get_performance_stats(self):
        """Получить статистику производительности"""
        with self.connection_lock:
            return {
                'active_connections': self.active_connections,
                'total_connections': self.total_connections,
                'rejected_connections': self.rejected_connections,
                'queue_size': self.connection_queue.qsize(),
                'max_connections': MAX_CONNECTIONS,
                'max_workers': MAX_WORKERS,
                'connection_queue_size': CONNECTION_QUEUE_SIZE
            }
    
    def log_performance_stats(self):
        """Записать статистику производительности"""
        stats = self.get_performance_stats()
        log_info(
            f"Статистика производительности - активных подключений: {stats['active_connections']}/{stats['max_connections']}, "
            f"размер очереди: {stats['queue_size']}/{stats['connection_queue_size']}, "
            f"всего подключений: {stats['total_connections']}, отклонено: {stats['rejected_connections']}"
        )
    
    def stop(self):
        """Остановить NTRIP сервер"""
        log_system_event('Завершение работы NTRIP сервера')
        
        self.running = False
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        if self.thread_pool:
            logger.log_system_event("Завершение работы пула потоков...")
            
            self.thread_pool.shutdown(wait=True)
            log_system_event("Пул потоков закрыт")
        
        while not self.connection_queue.empty():
            try:
                client_socket, client_address = self.connection_queue.get_nowait()
                client_socket.close()
                log_debug(f"Очистка подключений из очереди: {client_address}")
            except Empty:
                break
            except Exception as e:
                log_error(f"Исключение при очистке очереди подключений: {e}", exc_info=True)
        
        
        log_system_event(f'NTRIP сервер остановлен - всего подключений: {self.total_connections}, отклонено подключений: {self.rejected_connections}')
        log_system_event('NTRIP сервер закрыт')

