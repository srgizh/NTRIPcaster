#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import time
import signal
import logging
import psutil
import threading
import argparse
import os
from pathlib import Path
from threading import Thread

# Парсинг аргументов командной строки
parser = argparse.ArgumentParser(description='2RTK NTRIP Caster')
parser.add_argument('--config', type=str, help='Путь к файлу конфигурации')
args = parser.parse_args()

# Добавление корневой директории проекта в путь Python
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Если указан файл конфигурации, установить переменную окружения
if args.config:
    os.environ['NTRIP_CONFIG_FILE'] = args.config

# Импорт модулей конфигурации и ядра
from src import config
from src import logger
from src import forwarder
from src.database import DatabaseManager
from src.web import create_web_manager
from src.ntrip import NTRIPCaster
from src.connection import get_connection_manager

def setup_logging():
    """Настройка системы логирования"""
    # Инициализация модуля логирования
    logger.init_logging()
    
    # Установка уровней логирования для определенных модулей
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('socketio').setLevel(logging.WARNING)
    logging.getLogger('engineio').setLevel(logging.WARNING)
    
    # Запись системного лога запуска
    logger.log_system_event('Система логирования инициализирована')

def print_banner():
    """Вывод баннера запуска"""
    banner = f"""

    ██████╗ ██████╗ ████████╗██╗  ██╗
    ╚════██╗██╔══██╗╚══██╔══╝██║ ██╔╝
     █████╔╝██████╗╔   ██║   █████╔╝ 
    ██╔═══╝ ██╔══██╗   ██║   ██║  ██╗
    ███████╗██║  ██║   ██║   ██║  ██╗
    ╚══════╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝
    2RTK Ntrip Caster {config.VERSION}

Порт NTRIP: {config.NTRIP_PORT:<8} Порт Web-управления: {config.WEB_PORT:<8} 
Режим отладки: {str(config.DEBUG):<9} Максимум подключений: {config.MAX_CONNECTIONS:<8} 

    """
    print(banner)

def check_environment():
    """Проверка рабочей среды"""
    logger = logging.getLogger('main')
    
    # Проверка версии Python
    if sys.version_info < (3, 7):
        logger.error("Требуется Python 3.7 или выше")
        sys.exit(1)
    
    # Проверка необходимых директорий
    required_dirs = [
        Path(config.DATABASE_PATH).parent,
        Path(config.LOG_DIR)
    ]
    
    for dir_path in required_dirs:
        if not dir_path.exists():
            logger.info(f"Создание директории: {dir_path}")
            dir_path.mkdir(parents=True, exist_ok=True)
    
    # Проверка доступности портов
    import socket
    
    def check_port(port, name):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
            return True
        except OSError:
            logger.error(f"Порт {name} {port} уже занят")
            return False
    
    ports_ok = True
    ports_ok &= check_port(config.NTRIP_PORT, "NTRIP")
    ports_ok &= check_port(config.WEB_PORT, "Web")
    
    if not ports_ok:
        logger.error("Проверка портов не пройдена, проверьте занятость портов")
        sys.exit(1)
    
    logger.info("Проверка среды пройдена")

class ServiceManager:
    """Менеджер сервисов - унифицированное управление всеми сервисными компонентами"""
    
    def __init__(self):
        self.db_manager = None
        self.web_manager = None
        self.ntrip_caster = None
        self.web_thread = None
        self.running = False
        self.stopping = False  # Добавление флага остановки, чтобы предотвратить повторные вызовы
        self.start_time = None
        self.stats_thread = None
        self.stats_interval = 10  # Интервал вывода статистики (секунды)
        self.last_network_stats = None
        self.print_stats = False  # Управление выводом статистики в консоль
        self.system_stats_cache = {}  # Кеш системной статистики для Web API
        
    def start_all_services(self):
        """Запуск всех сервисов"""
        try:
            self.start_time = time.time()
            logger.log_system_event(f'Запуск 2RTK NTRIP Caster v{config.VERSION}')
            
            # 1. Инициализация базы данных
            self.db_manager = DatabaseManager()
            self.db_manager.init_database()
            logger.log_system_event('База данных инициализирована')
            
            # 2. Инициализация и запуск пересылки данных
            forwarder.initialize()
            forwarder.start_forwarder()
            logger.log_system_event('Пересылка данных инициализирована')
            
            # 3. Парсинг RTCM теперь интегрирован в connection_manager, не требует отдельного запуска
            logger.log_system_event('Парсер RTCM интегрирован')
            
            # 4. Запуск веб-интерфейса управления
            self._start_web_interface()
            
            # 5. Запуск NTRIP сервера (в отдельном потоке)
            self.ntrip_caster = NTRIPCaster(self.db_manager)
            self.ntrip_thread = threading.Thread(target=self.ntrip_caster.start, daemon=True)
            self.ntrip_thread.start()
            time.sleep(1)  # Ожидание запуска NTRIP сервера
            
            # 6. Регистрация обработчиков сигналов
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            self.running = True
            logger.log_system_event(f'Все сервисы запущены - Порт NTRIP: {config.NTRIP_PORT}, Порт Web: {config.WEB_PORT}')
            
            # Запуск потока мониторинга статистики
            self._start_stats_monitor()
            
            # Главный цикл - поддержание работы сервисов
            self._main_loop()
            
        except Exception as e:
            logger.log_error(f"Ошибка при запуске сервисов: {e}", exc_info=True)
            self.stop_all_services()
            raise
    
    def _start_web_interface(self):
        """Запуск веб-интерфейса управления"""
        from src.web import set_server_instance
        self.web_manager = create_web_manager(
            self.db_manager, 
            forwarder.get_forwarder(), 
            self.start_time
        )
        # Установка экземпляра сервера для использования в Web API
        set_server_instance(self)
        self.web_manager.start_rtcm_parsing()
        
        def run_web():
            self.web_manager.run(host=config.HOST, port=config.WEB_PORT, debug=False)
        
        self.web_thread = Thread(target=run_web, daemon=True)
        self.web_thread.start()
        
        # Отображение всех доступных адресов веб-интерфейса управления
        web_urls = config.get_display_urls(config.WEB_PORT, "Веб-интерфейс управления")
        if len(web_urls) == 1:
            logger.log_info(f'Веб-интерфейс управления запущен, адрес управления: {web_urls[0]}')
        else:
            logger.log_system_event('Веб-интерфейс управления запущен, доступен по следующим адресам:')
            for url in web_urls:
                logger.log_system_event(f'  - {url}')
    
    def _start_stats_monitor(self):
        """Запуск потока мониторинга статистики"""
        self.stats_thread = Thread(target=self._stats_monitor_worker, daemon=True)
        self.stats_thread.start()
 
    def _stats_monitor_worker(self):
        """Рабочий поток мониторинга статистики"""
        while self.running:
            try:
                time.sleep(self.stats_interval)
                if self.running:
                    self._update_system_stats()
            except Exception as e:
                logger.log_error(f"Исключение в мониторинге статистики: {e}", exc_info=True)
    
    def _update_system_stats(self):
        """Обновление системной статистики в кеше"""
        try:
            # Получение данных производительности системы
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # Получение сетевой статистики
            network_stats = psutil.net_io_counters()
            network_bandwidth = self._calculate_network_bandwidth(network_stats)
            
            # Получение статистики NTRIP сервера
            ntrip_stats = self.ntrip_caster.get_performance_stats() if self.ntrip_caster else {}
            
            # Получение статистики менеджера подключений
            conn_manager = get_connection_manager()
            conn_stats = conn_manager.get_statistics()
            
            # Расчет времени работы
            uptime = time.time() - self.start_time if self.start_time else 0
            uptime_str = self._format_uptime(uptime)
            
            # Расчет статистики передачи данных
            total_data_bytes = sum(mount['total_bytes'] for mount in conn_stats.get('mounts', []) if 'total_bytes' in mount)
            total_data_mb = total_data_bytes / (1024 * 1024)
            
            # Обновление кеша
            self.system_stats_cache = {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'uptime': uptime,  # Сохранение времени работы в числовом формате
                'uptime_str': uptime_str,  # Сохранение форматированной строки времени работы
                'cpu_percent': cpu_percent,
                'memory': memory,
                'network_bandwidth': network_bandwidth,
                'ntrip_stats': ntrip_stats,
                'conn_stats': conn_stats,
                'total_data_mb': total_data_mb
            }
            
        except Exception as e:
            logger.log_error(f"Ошибка при обновлении статистики: {e}", exc_info=True)
    

    
    def get_system_stats(self):
        """Получение системной статистики для использования в Web API"""
        try:
            stats = self.system_stats_cache.copy()
            if not stats:
                # Если кеш пуст, немедленно обновить один раз
                self._update_system_stats()
                stats = self.system_stats_cache.copy()
            
            # Форматирование данных для использования фронтендом
            if stats:
                memory_info = stats.get('memory')
                network_info = stats.get('network_bandwidth', {})
                
                return {
                    'timestamp': stats.get('timestamp'),
                    'uptime': stats.get('uptime', 0),  # Возврат времени работы в числовом формате
                    'cpu_percent': round(stats.get('cpu_percent', 0), 1),
                    'memory': {
                        'percent': round(getattr(memory_info, 'percent', 0), 1),
                        'used': getattr(memory_info, 'used', 0),
                        'total': getattr(memory_info, 'total', 0)
                    },
                    'network_bandwidth': {
                        'sent_rate': network_info.get('sent_rate', 0) if isinstance(network_info, dict) else 0,
                        'recv_rate': network_info.get('recv_rate', 0) if isinstance(network_info, dict) else 0
                    },
                    'connections': {
                        'active': stats.get('ntrip_stats', {}).get('active_connections', 0),
                        'total': stats.get('ntrip_stats', {}).get('total_connections', 0),
                        'rejected': stats.get('ntrip_stats', {}).get('rejected_connections', 0),
                        'max_concurrent': stats.get('ntrip_stats', {}).get('max_concurrent', 0)
                    },
                    'mounts': stats.get('conn_stats', {}).get('mounts', {}),
                    'users': stats.get('conn_stats', {}).get('users', {}),
                    'data_transfer': {
                        'total_bytes': stats.get('total_data_mb', 0) * 1024 * 1024
                    }
                }
            return {}
        except Exception as e:
            logger.log_error(f"Ошибка при получении системной статистики: {e}", exc_info=True)
            return {}
    
    def set_print_stats(self, enabled):
        """Установка вывода статистики в консоль"""
        self.print_stats = enabled
        if enabled:
            logger.log_system_event('Вывод статистики в консоль включен')
        else:
            logger.log_system_event('Вывод статистики в консоль отключен')
    
    def _calculate_network_bandwidth(self, current_stats):
        """Расчет сетевой пропускной способности"""
        if self.last_network_stats is None:
            self.last_network_stats = (current_stats, time.time())
            return "Вычисление..."
        
        last_stats, last_time = self.last_network_stats
        current_time = time.time()
        time_diff = current_time - last_time
        
        if time_diff <= 0:
            return "Вычисление..."
        
        bytes_sent_diff = current_stats.bytes_sent - last_stats.bytes_sent
        bytes_recv_diff = current_stats.bytes_recv - last_stats.bytes_recv
        
        upload_mbps = (bytes_sent_diff * 8) / (time_diff * 1024 * 1024)
        download_mbps = (bytes_recv_diff * 8) / (time_diff * 1024 * 1024)
        total_mbps = upload_mbps + download_mbps
        
        self.last_network_stats = (current_stats, current_time)
        
        return f"↑{upload_mbps:.2f} Mbps ↓{download_mbps:.2f} Mbps (Итого: {total_mbps:.2f} Mbps)"
    
    def _format_uptime(self, seconds):
        """Форматирование времени работы"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if days > 0:
            return f"{days} дн. {hours} ч. {minutes} мин."
        elif hours > 0:
            return f"{hours} ч. {minutes} мин."
        else:
            return f"{minutes} мин. {secs} сек."

    def _main_loop(self):
        """Главный цикл - мониторинг состояния сервисов"""
        while self.running:
            try:
                # Проверка состояния каждого сервиса
                if self.ntrip_caster and not self.ntrip_caster.running:
                    logger.log_error('NTRIP сервер неожиданно остановлен')
                    break
                    
                if self.web_thread and not self.web_thread.is_alive():
                    logger.log_error('Web сервис неожиданно остановлен')
                    break
                
                # Короткая пауза для избежания высокой загрузки CPU
                time.sleep(1)
                
            except Exception as e:
                logger.log_error(f"Исключение в главном цикле: {e}", exc_info=True)
                break
    
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов"""
        if self.stopping:
            logger.log_system_event(f'Получен сигнал {signum}, но сервисы уже закрываются, игнорируем повторный сигнал')
            return
        logger.log_system_event(f'Получен сигнал {signum}, начинаем закрытие всех сервисов')
        self.stop_all_services()
    
    def stop_all_services(self):
        """Остановка всех сервисов"""
        if self.stopping:
            logger.log_system_event('Сервисы уже закрываются, избегаем повторного вызова')
            return
            
        self.stopping = True
        logger.log_system_event('Закрытие всех сервисов')
        
        try:
            self.running = False
            
            # Ожидание завершения потока мониторинга статистики
            if self.stats_thread and self.stats_thread.is_alive():
                logger.log_system_event('Остановка потока мониторинга статистики')
                self.stats_thread.join(timeout=2)
            
            # Остановка NTRIP сервера
            if self.ntrip_caster:
                try:
                    self.ntrip_caster.stop()
                except Exception as e:
                    logger.log_error(f'Ошибка при остановке NTRIP сервера: {e}')
        
            # Остановка пересылки данных
            try:
                forwarder.stop_forwarder()
            except Exception as e:
                logger.log_error(f'Ошибка при остановке пересылки данных: {e}')
            
            # Остановка Web менеджера
            if self.web_manager:
                try:
                    self.web_manager.stop_rtcm_parsing()
                except Exception as e:
                    logger.log_error(f'Ошибка при остановке Web менеджера: {e}')
            
            logger.log_system_event('Все сервисы закрыты')
            
        except Exception as e:
            logger.log_error(f'Исключение при закрытии сервисов: {e}')
        finally:
            # Убедиться, что флаг остановки сброшен (хотя программа скоро завершится)
            self.stopping = False

# Глобальный экземпляр сервера
server = None

def get_server_instance():
    """Получение экземпляра сервера"""
    return server

def main():
    """Главная функция"""
    global server
    try:
        # Настройка логирования
        setup_logging()
        main_logger = logger.get_logger('main')
        
        # Вывод информации о запуске
        print_banner()
        
        # Проверка среды
        check_environment()
        
        # Инициализация конфигурации
        config.init_config()
        logger.log_system_event('Конфигурация инициализирована')
        
        # Создание экземпляра сервера и запуск всех сервисов
        server = ServiceManager()
        globals()['server'] = server  # Установка глобальной переменной
        server.start_all_services()
        
    except KeyboardInterrupt:
        logger.log_system_event('Получен сигнал прерывания, закрываем сервисы')
    except Exception as e:
        logger.log_error(f"Ошибка запуска: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if server:
            server.stop_all_services()
        logger.log_system_event('Программа завершена')
        logger.shutdown_logging()

if __name__ == '__main__':
    main()