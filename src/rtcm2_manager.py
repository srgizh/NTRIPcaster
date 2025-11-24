# -*- coding: utf-8 -*-
"""
Менеджер парсинга RTCM2
"""

import threading
import time
from typing import Dict, Optional, Callable, Any
from .logger import log_debug, log_info, log_warning, log_error


class RTCM2ParserManager:
    """Менеджер парсинга RTCM2 - совместимость с оригинальным интерфейсом parser_manager"""
    
    def __init__(self):
        self.parsers: Dict[str, Any] = {}  # Экземпляры RTCMParserThread
        self.web_parsers: Dict[str, Any] = {}  # Экземпляры потоков парсинга Web (отдельное управление)
        self.str_parsers: Dict[str, Any] = {}  # Экземпляры потоков исправления STR (отдельное управление)
        self.current_web_mount: Optional[str] = None  # Текущая активная точка монтирования для парсинга Web
        self.lock = threading.RLock()
        log_info("Менеджер парсинга данных RTCM2 инициализирован")

    def start_parser(self, mount_name: str, mode: str = "str_fix", duration: int = 30, 
                     push_callback: Optional[Callable[[Dict], None]] = None) -> bool:
        """Запуск парсера (совместимость с оригинальным интерфейсом)"""
        with self.lock:
            # Если парсер уже существует, сначала остановить его
            if mount_name in self.parsers:
                self.stop_parser(mount_name)
            
            try:
                # Динамический импорт для избежания циклических импортов
                from .rtcm2 import start_str_fix_parser, start_web_parser
                
                if mode == "str_fix":
                    parser = start_str_fix_parser(mount_name, duration, push_callback)
                    # Режим исправления STR: добавление в словарь парсеров STR
                    self.str_parsers[mount_name] = parser
                    log_info(f"Запущен парсинг RTCM для точки монтирования {mount_name} для исправления STR, длительность: {duration}s")
                else:  # realtime_web
                    parser = start_web_parser(mount_name, push_callback)
                    # Режим парсинга Web: добавление в словарь парсеров Web
                    self.web_parsers[mount_name] = parser
                    log_info(f"Запущен парсинг данных RTCM для Web для точки монтирования {mount_name}")
                
                # Сохранение оригинальной совместимости
                self.parsers[mount_name] = parser
                log_info(f"Запущен парсинг данных RTCM для точки монтирования {mount_name}, режим: {mode}")
                return True
            except Exception as e:
                log_error(f"Ошибка при запуске парсинга данных RTCM для точки монтирования {mount_name}: {str(e)}")
                return False

    def stop_parser(self, mount_name: str):
        """Остановка парсера (совместимость с оригинальным интерфейсом)"""
        with self.lock:
            if mount_name in self.parsers:
                parser = self.parsers[mount_name]
                parser.stop()
                del self.parsers[mount_name]
                
                # Удаление из соответствующего классифицированного словаря
                if mount_name in self.web_parsers:
                    del self.web_parsers[mount_name]
                    log_info(f"Парсинг данных RTCM для Web для точки монтирования {mount_name} закрыт")

                elif mount_name in self.str_parsers:
                    del self.str_parsers[mount_name]
                    log_info(f"Парсинг исправления STR для точки монтирования {mount_name} закрыт")

                else:
                    log_info(f"Парсинг данных RTCM для точки монтирования {mount_name} закрыт")
             
    def get_result(self, mount_name: str) -> Optional[Dict]:
        """Получение результатов парсинга (совместимость с оригинальным интерфейсом)"""
        with self.lock:
            parser = self.parsers.get(mount_name)
            if parser:
                # Получение результатов парсинга из rtcm2.py и преобразование в совместимый формат
                result = parser.result.copy()
                
                # Преобразование в формат, ожидаемый оригинальным интерфейсом
                converted_result = self._convert_result_format(result)
                log_debug(f"Получены результаты парсинга для точки монтирования {mount_name}: {converted_result is not None}")
                return converted_result
            
            log_debug(f"Парсер не найден для точки монтирования {mount_name}")
            return None

    def _convert_result_format(self, result: Dict) -> Dict:
        """Преобразование формата результатов rtcm2.py в формат, ожидаемый оригинальным интерфейсом"""
        converted = {
            "mount": result.get("mount"),
            "bitrate": result.get("bitrate", 0),
            "total_messages": sum(result.get("message_stats", {}).get("types", {}).values()),
            "last_update": time.time()
        }
        
        # Преобразование информации о местоположении
        location = result.get("location")
        if location:
            converted.update({
                "station_id": location.get("station_id"),
                "lat": location.get("lat"),
                "lon": location.get("lon"),
                "country": location.get("country"),
                "city": location.get("city")
            })
        
        # Преобразование информации об устройстве
        device = result.get("device")
        if device:
            converted.update({
                "receiver": device.get("receiver"),
                "antenna": device.get("antenna"),
                "firmware": device.get("firmware")
            })
        
        # Преобразование статистики сообщений
        msg_stats = result.get("message_stats", {})
        if msg_stats:
            # Комбинация систем GNSS
            gnss_set = msg_stats.get("gnss", set())
            converted["gnss_combined"] = "+".join(sorted(gnss_set)) if gnss_set else "N/A"
            
            # Комбинация несущих
            carriers_set = msg_stats.get("carriers", set())
            converted["carrier_combined"] = "+".join(sorted(carriers_set)) if carriers_set else "N/A"
            
            # Строка типов сообщений
            frequency = msg_stats.get("frequency", {})
            if frequency:
                msg_types_list = [f"{msg_id}({freq})" for msg_id, freq in frequency.items()]
                converted["message_types_str"] = ",".join(msg_types_list)
            else:
                converted["message_types_str"] = "N/A"
        
        return converted

    def stop_all(self):
        """Остановка всех парсеров (совместимость с оригинальным интерфейсом)"""
        with self.lock:
            for mount_name in list(self.parsers.keys()):
                self.stop_parser(mount_name)
            log_info("Все парсеры остановлены")

    # Методы, связанные с режимом Web (совместимость с оригинальным интерфейсом)
    def acquire_parser(self, mount_name: str, push_callback: Optional[Callable[[Dict], None]] = None) -> Optional[Dict]:
        """Получение парсера (режим Web)"""
        success = self.start_parser(mount_name, mode="realtime_web", push_callback=push_callback)
        if success:
            return self.get_result(mount_name)
        return None

    def release_parser(self, mount_name: str):
        """Освобождение парсера (режим Web)"""
        self.stop_parser(mount_name)

    def start_realtime_parsing(self, mount_name: str, push_callback: Optional[Callable[[Dict], None]] = None) -> bool:
        """Запуск парсинга в реальном времени (режим Web) - улучшенная версия: сначала очистить предыдущий поток парсинга Web, затем запустить новый"""
        with self.lock:
            # Шаг 1: Очистка предыдущего потока парсинга Web (если существует)
            if self.current_web_mount and self.current_web_mount != mount_name:
                log_info(f"Обнаружен предыдущий поток парсинга Web для точки монтирования {self.current_web_mount}, подготовка к очистке")
                self._stop_web_parser_only(self.current_web_mount)
            
            # Шаг 2: Если текущая точка монтирования уже имеет поток парсинга Web, также сначала остановить
            if mount_name in self.web_parsers:
                log_info(f"Текущая точка монтирования {mount_name} уже имеет поток парсинга Web, сначала остановить")
                self._stop_web_parser_only(mount_name)
            
            # Шаг 3: Запуск нового потока парсинга Web
            success = self.start_parser(mount_name, mode="realtime_web", push_callback=push_callback)
            if success:
                # Обновление текущей активной точки монтирования для парсинга Web
                self.current_web_mount = mount_name
                log_info(f"Поток парсинга Web успешно запущен, текущая активная точка монтирования: {mount_name}")
            
            return success

    def _stop_web_parser_only(self, mount_name: str):
        """Остановка только потока парсинга Web для указанной точки монтирования, не влияет на поток исправления STR"""
        if mount_name in self.web_parsers:
            parser = self.web_parsers[mount_name]
            parser.stop()
            del self.web_parsers[mount_name]
            
            # Удаление из общего словаря (если существует)
            if mount_name in self.parsers:
                del self.parsers[mount_name]
            
            # Очистка маркера текущей активной точки монтирования
            if self.current_web_mount == mount_name:
                self.current_web_mount = None
            
            log_info(f"Поток парсинга Web для точки монтирования {mount_name} остановлен, поток исправления STR не затронут")

    def stop_realtime_parsing(self):
        """Остановка всего парсинга в реальном времени (режим Web) - улучшенная версия: остановить только потоки парсинга Web, защитить потоки исправления STR"""
        with self.lock:
            # Остановить только потоки парсинга Web, не влияя на потоки исправления STR
            web_mounts = list(self.web_parsers.keys())
            for mount_name in web_mounts:
                self._stop_web_parser_only(mount_name)
            
            # Очистка текущей активной точки монтирования
            self.current_web_mount = None
            
            if web_mounts:
                log_info(f"Остановлены все потоки парсинга Web для точек монтирования: {', '.join(web_mounts)}, потоки исправления STR продолжают работать")
            else:
                log_info("Нет активных потоков парсинга Web для остановки")

    def update_parsing_heartbeat(self, mount_name: str):
        """Обновление пульса парсинга (совместимость с оригинальным интерфейсом, пока не требует реализации)"""
        pass

    def get_parsed_mount_data(self, mount_name: str, limit: int = None) -> Optional[Dict]:
        """Получение данных парсинга точки монтирования (совместимость с оригинальным интерфейсом)"""
        return self.get_result(mount_name)

    def get_mount_statistics(self, mount_name: str) -> Optional[Dict]:
        """Получение статистики точки монтирования (совместимость с оригинальным интерфейсом)"""
        result = self.get_result(mount_name)
        if result:
            return {
                "bitrate": result.get("bitrate", 0),
                "total_messages": result.get("total_messages", 0),
                "last_update": result.get("last_update")
            }
        return None

    def get_parser_status(self) -> Dict:
        """Получение информации о состоянии парсера"""
        with self.lock:
            return {
                "total_parsers": len(self.parsers),
                "web_parsers": len(self.web_parsers),
                "str_parsers": len(self.str_parsers),
                "current_web_mount": self.current_web_mount,
                "web_mounts": list(self.web_parsers.keys()),
                "str_mounts": list(self.str_parsers.keys())
            }

    def is_web_parsing_active(self, mount_name: str) -> bool:
        """Проверка наличия активного потока парсинга Web для указанной точки монтирования"""
        with self.lock:
            return mount_name in self.web_parsers

    def is_str_parsing_active(self, mount_name: str) -> bool:
        """Проверка наличия активного потока исправления STR для указанной точки монтирования"""
        with self.lock:
            return mount_name in self.str_parsers

    def get_current_web_mount(self) -> Optional[str]:
        """Получение текущей активной точки монтирования для парсинга Web"""
        return self.current_web_mount


# Глобальный менеджер-синглтон
parser_manager = RTCM2ParserManager()