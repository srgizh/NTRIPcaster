#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
import threading

# Импорт конфигурации
try:
    from . import config
except ImportError:
   
    class DefaultConfig:
        LOG_LEVEL = 'INFO'
        LOG_DIR = 'logs'
        LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        LOG_FILES = {
            'main': 'main.log',
            'ntrip': 'ntrip.log',
            'error': 'errors.log'
        }
        LOG_MAX_SIZE = 10 * 1024 * 1024  # 10MB
        LOG_BACKUP_COUNT = 5
        DEBUG = False
    
    config = DefaultConfig()

class NTRIPLogger:
    """
    Менеджер логирования NTRIP Caster

    """
    
    _instance = None
    _lock = threading.Lock()
    _web_instance = None  
    
    def __new__(cls):
        """Реализация паттерна Singleton"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(NTRIPLogger, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Инициализация системы логирования"""
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self._loggers = {}
        self._setup_logging()
    
    def _setup_logging(self):
        """Настройка системы логирования"""
        
        log_dir = Path(config.LOG_DIR)
        log_dir.mkdir(exist_ok=True)
        
        
        formatter = logging.Formatter(
            config.LOG_FORMAT,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Создание регистраторов логов различных типов
        self._create_logger('main', config.LOG_FILES['main'], logging.INFO, formatter)
        self._create_logger('ntrip', config.LOG_FILES['ntrip'], logging.DEBUG, formatter)
        self._create_logger('error', config.LOG_FILES['errors'], logging.ERROR, formatter)
        
        self._create_root_logger(formatter)
    
    def _create_logger(self, name, filename, level, formatter):
        """Создание регистратора логов указанного типа"""
        logger = logging.getLogger(f'ntrip.{name}')
        logger.setLevel(level)
        
        logger.handlers.clear()
        
        file_path = os.path.join(config.LOG_DIR, filename)
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=config.LOG_MAX_SIZE,
            backupCount=config.LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        if config.DEBUG or level >= logging.ERROR:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        logger.propagate = False
        
        self._loggers[name] = logger
    
    def _create_root_logger(self, formatter):
        """Создание корневого регистратора логов"""
        root_logger = logging.getLogger('ntrip')
        root_logger.setLevel(getattr(logging, config.LOG_LEVEL.upper()))
        
        root_logger.handlers.clear()
        
        main_file_path = os.path.join(config.LOG_DIR, config.LOG_FILES['main'])
        main_handler = RotatingFileHandler(
            main_file_path,
            maxBytes=config.LOG_MAX_SIZE,
            backupCount=config.LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        main_handler.setLevel(logging.INFO)
        main_handler.setFormatter(formatter)
        root_logger.addHandler(main_handler)
        
        error_file_path = os.path.join(config.LOG_DIR, config.LOG_FILES['errors'])
        error_handler = RotatingFileHandler(
            error_file_path,
            maxBytes=config.LOG_MAX_SIZE,
            backupCount=config.LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)
        
        if config.DEBUG:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(getattr(logging, config.LOG_LEVEL.upper()))
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
        
        self._loggers['root'] = root_logger
    
    def get_logger(self, name='root'):
        """Получение регистратора логов с указанным именем"""
        if name in self._loggers:
            return self._loggers[name]
        else:
            
            logger = logging.getLogger(f'ntrip.{name}')
            logger.setLevel(getattr(logging, config.LOG_LEVEL.upper()))
            return logger
    
    @classmethod
    def set_web_instance(cls, web_instance):
        """
        Установка ссылки на экземпляр Web для рассылки логов в реальном времени

        """
        cls._web_instance = web_instance
    
    def _push_to_web(self, message, log_type='info'):
        """
        Отправка сообщения лога на Web фронтенд
            log_type: Тип лога ('info', 'warning', 'error', 'debug')
        """
        # Фильтрация частых логов, чтобы избежать перегрузки фронтенда
        filtered_keywords = [
            'Обновление активности пользователя', 'MSM', 'Спутник', 'Отправка данных', 'Подключение клиента',
            'RTCM data', 'Performance:', 'Database', 'bytes for mount'
        ]
        
        # Проверка наличия ключевых слов для фильтрации
        if any(keyword in message for keyword in filtered_keywords):
            return  # Не отправлять эти частые логи на фронтенд
            
        if self._web_instance and hasattr(self._web_instance, 'push_log_message'):
            try:
                self._web_instance.push_log_message(message, log_type)
            except Exception:
                # Избегаем влияния сбоя рассылки логов на основную функциональность
                pass
    
    def log_info(self, message, module='main'):
        """Запись информационного лога"""
        logger = self.get_logger(module)
        logger.info(message)
        self._push_to_web(message, 'info')
    
    def log_debug(self, message, module='main'):
        """Запись отладочного лога"""
        logger = self.get_logger(module)
        logger.debug(message)
        # Не отправлять отладочные логи на фронтенд, чтобы избежать перегрузки
        # if config.DEBUG:  # Отправлять отладочные логи только в режиме отладки
        #     self._push_to_web(message, 'debug')
    
    def log_warning(self, message, module='main'):
        """Запись предупреждающего лога"""
        logger = self.get_logger(module)
        logger.warning(message)
        self._push_to_web(message, 'warning')
    
    def log_error(self, message, module='error', exc_info=False):
        """Запись лога об ошибке"""
        logger = self.get_logger(module)
        logger.error(message, exc_info=exc_info)
        self._push_to_web(message, 'error')
    
    def log_critical(self, message, module='error', exc_info=False):
        """Запись лога о критической ошибке"""
        logger = self.get_logger(module)
        logger.critical(message, exc_info=exc_info)
        self._push_to_web(message, 'error')
    
    def log_ntrip_request(self, method, path, client_ip, user_agent=''):
        """Запись лога NTRIP запроса"""
        message = f"NTRIP {method} request: {path} from {client_ip}"
        if user_agent:
            message += f" (User-Agent: {user_agent})"
        self.get_logger('ntrip').info(message)
    
    def log_ntrip_response(self, method, path, status_code, client_ip):
        """Запись лога NTRIP ответа"""
        message = f"NTRIP {method} response: {status_code} for {path} to {client_ip}"
        self.get_logger('ntrip').info(message)
    
    def log_client_connect(self, username, mount, client_ip, ntrip_version):
        """Запись лога подключения клиента"""
        message = f"Client connected: {username}@{mount} from {client_ip} (NTRIP {ntrip_version})"
        self.get_logger('ntrip').info(message)
    
    def log_client_disconnect(self, username, mount, client_ip, reason=''):
        """Запись лога отключения клиента"""
        message = f"Client disconnected: {username}@{mount} from {client_ip}"
        if reason:
            message += f" (Reason: {reason})"
        self.get_logger('ntrip').info(message)
    
    def log_data_transfer(self, mount, bytes_sent, client_count):
        """Запись лога передачи данных"""
        message = f"Data transfer: {bytes_sent} bytes sent to {client_count} clients for mount {mount}"
        self.get_logger('ntrip').debug(message)
    
    def log_mount_operation(self, operation, mount, username='', details=''):
        """Запись лога операции с точкой монтирования"""
        message = f"Mount {operation}: {mount}"
        if username:
            message += f" by {username}"
        if details:
            message += f" ({details})"
        self.get_logger('ntrip').info(message)
    
    def log_authentication(self, username, mount, success, client_ip, reason=''):
        """Запись лога аутентификации"""
        status = 'SUCCESS' if success else 'FAILED'
        message = f"Authentication {status}: {username}@{mount} from {client_ip}"
        if reason:
            message += f" (Reason: {reason})"
        
        if success:
            self.get_logger('ntrip').info(message)
        else:
            self.get_logger('error').warning(message)
    
    def log_system_event(self, event, details=''):
        """Запись лога системного события"""
        message = f"System event: {event}"
        if details:
            message += f" - {details}"
        self.get_logger('main').info(message)
        self._push_to_web(f"Системное событие: {event}" + (f" - {details}" if details else ""), 'info')
    
    def log_performance(self, metric, value, unit=''):
        """Запись лога показателей производительности"""
        message = f"Performance: {metric} = {value}"
        if unit:
            # Убеждаемся, что строка единиц измерения не будет неправильно интерпретирована как символ форматирования
            safe_unit = str(unit).replace('%', '%%')
            message += f" {safe_unit}"
        self.get_logger('main').debug(message)
    
    def log_rtcm_data(self, mount, message_type, message_length, client_count):
        """Запись лога обработки данных RTCM"""
        message = f"RTCM data: Type {message_type}, {message_length} bytes for mount {mount}, sent to {client_count} clients"
        self.get_logger('ntrip').debug(message)
    
    def log_database_operation(self, operation, table, success, details=''):
        """Запись лога операции с базой данных"""
        status = 'SUCCESS' if success else 'FAILED'
        message = f"Database {operation} {status}: {table}"
        if details:
            message += f" ({details})"
        
        if success:
            self.get_logger('main').debug(message)
        else:
            self.get_logger('error').error(message)
    
    def log_web_request(self, method, path, client_ip, status_code, response_time=None):
        """Запись лога Web запроса"""
        message = f"Web {method} {path} from {client_ip} - {status_code}"
        if response_time is not None:
            message += f" ({response_time:.3f}s)"
        self.get_logger('main').info(message)
    
    def shutdown(self):
        """Завершение работы системы логирования"""
        for logger in self._loggers.values():
            for handler in logger.handlers:
                handler.close()
                logger.removeHandler(handler)
        
        
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            handler.close()
            root_logger.removeHandler(handler)


_logger_instance = None
_logger_lock = threading.Lock()

def get_logger(name='root'):
    """Получение глобального экземпляра логгера"""
    global _logger_instance
    if _logger_instance is None:
        with _logger_lock:
            if _logger_instance is None:
                _logger_instance = NTRIPLogger()
    return _logger_instance.get_logger(name)

def init_logging():
    """Инициализация системы логирования"""
    global _logger_instance
    if _logger_instance is None:
        with _logger_lock:
            if _logger_instance is None:
                _logger_instance = NTRIPLogger()
    return _logger_instance

def set_web_instance(web_instance):
    """Установка ссылки на экземпляр Web для рассылки логов в реальном времени"""
    NTRIPLogger.set_web_instance(web_instance)


def log_info(message, module='main'):
    """Запись информационного лога"""
    logger_instance = init_logging()
    logger_instance.log_info(message, module)

def log_debug(message, module='main'):
    """Запись отладочного лога"""
    logger_instance = init_logging()
    logger_instance.log_debug(message, module)

def log_warning(message, module='main'):
    """Запись предупреждающего лога"""
    logger_instance = init_logging()
    logger_instance.log_warning(message, module)

def log_error(message, module='error', exc_info=False):
    """Запись лога об ошибке"""
    logger_instance = init_logging()
    logger_instance.log_error(message, module, exc_info)

def log_critical(message, module='error', exc_info=False):
    """Запись лога о критической ошибке"""
    logger_instance = init_logging()
    logger_instance.log_critical(message, module, exc_info)

def log_ntrip_request(method, path, client_ip, user_agent=''):
    """Запись лога NTRIP запроса"""
    logger_instance = init_logging()
    logger_instance.log_ntrip_request(method, path, client_ip, user_agent)

def log_ntrip_response(method, path, status_code, client_ip):
    """Запись лога NTRIP ответа"""
    logger_instance = init_logging()
    logger_instance.log_ntrip_response(method, path, status_code, client_ip)

def log_client_connect(username, mount, client_ip, ntrip_version):
    """Запись лога подключения клиента"""
    logger_instance = init_logging()
    logger_instance.log_client_connect(username, mount, client_ip, ntrip_version)

def log_client_disconnect(username, mount, client_ip, reason=''):
    """Запись лога отключения клиента"""
    logger_instance = init_logging()
    logger_instance.log_client_disconnect(username, mount, client_ip, reason)

def log_data_transfer(mount, bytes_sent, client_count):
    """Запись лога передачи данных"""
    logger_instance = init_logging()
    logger_instance.log_data_transfer(mount, bytes_sent, client_count)

def log_mount_operation(operation, mount, username='', details=''):
    """Запись лога операции с точкой монтирования"""
    logger_instance = init_logging()
    logger_instance.log_mount_operation(operation, mount, username, details)

def log_authentication(username, mount, success, client_ip, reason=''):
    """Запись лога аутентификации"""
    logger_instance = init_logging()
    logger_instance.log_authentication(username, mount, success, client_ip, reason)

def log_system_event(event, details=''):
    """Запись лога системного события"""
    logger_instance = init_logging()
    logger_instance.log_system_event(event, details)

def log_performance(metric, value, unit=''):
    """Запись лога показателей производительности"""
    logger_instance = init_logging()
    logger_instance.log_performance(metric, value, unit)

def log_rtcm_data(mount, message_type, message_length, client_count):
    """Запись лога обработки данных RTCM"""
    logger_instance = init_logging()
    logger_instance.log_rtcm_data(mount, message_type, message_length, client_count)

def log_database_operation(operation, table, success, details=''):
    """Запись лога операции с базой данных"""
    logger_instance = init_logging()
    logger_instance.log_database_operation(operation, table, success, details)

def log_web_request(method, path, client_ip, status_code, response_time=None):
    """Запись лога Web запроса"""
    logger_instance = init_logging()
    logger_instance.log_web_request(method, path, client_ip, status_code, response_time)

def shutdown_logging():
    """Завершение работы системы логирования"""
    global _logger_instance
    if _logger_instance is not None:
        _logger_instance.shutdown()
        _logger_instance = None


logger = get_logger('main')
ntrip_logger = get_logger('ntrip')
error_logger = get_logger('error')

