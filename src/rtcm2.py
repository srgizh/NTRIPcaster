# -*- coding: utf-8 -*-
"""
Модуль парсинга данных RTCM (оптимизированная версия)
Предоставляет функциональность парсинга сообщений RTCM, исправления STR и визуализации данных в реальном времени, оптимизирована логика запросов информации о созвездиях
"""

# Импорт стандартных библиотек
import threading
import time
import socket
import logging
from typing import Dict, Optional, Callable, List, Tuple
from collections import defaultdict

# Импорт сторонних библиотек
from pyrtcm import RTCMReader, RTCMMessage, parse_msm
from pyproj import Transformer

# Импорт локальных модулей
from . import forwarder
from . import logger
from .logger import log_debug, log_info, log_warning, log_error, log_critical

# Таблица отображения кодов стран (2 символа -> 3 символа) - полное отображение ISO 3166-1
COUNTRY_CODE_MAP = {
    # Азия
    "CN": "CHN", "JP": "JPN", "KR": "KOR", "IN": "IND", "ID": "IDN", "TH": "THA",
    "VN": "VNM", "MY": "MYS", "SG": "SGP", "PH": "PHL", "BD": "BGD", "PK": "PAK",
    "LK": "LKA", "MM": "MMR", "KH": "KHM", "LA": "LAO", "BN": "BRN", "MN": "MNG",
    "KZ": "KAZ", "UZ": "UZB", "TM": "TKM", "KG": "KGZ", "TJ": "TJK", "AF": "AFG",
    "IR": "IRN", "IQ": "IRQ", "SY": "SYR", "JO": "JOR", "LB": "LBN", "IL": "ISR",
    "PS": "PSE", "SA": "SAU", "AE": "ARE", "QA": "QAT", "BH": "BHR", "KW": "KWT",
    "OM": "OMN", "YE": "YEM", "TR": "TUR", "GE": "GEO", "AM": "ARM", "AZ": "AZE",
    "CY": "CYP", "TW": "TWN", "HK": "HKG", "MO": "MAC", "BT": "BTN", "MV": "MDV",
    "NP": "NPL", "TL": "TLS",
    
    # Европа
    "GB": "GBR", "DE": "DEU", "FR": "FRA", "IT": "ITA", "ES": "ESP", "PT": "PRT",
    "NL": "NLD", "BE": "BEL", "CH": "CHE", "AT": "AUT", "SE": "SWE", "NO": "NOR",
    "DK": "DNK", "FI": "FIN", "IS": "ISL", "IE": "IRL", "LU": "LUX", "MT": "MLT",
    "PL": "POL", "CZ": "CZE", "SK": "SVK", "HU": "HUN", "SI": "SVN", "HR": "HRV",
    "BA": "BIH", "RS": "SRB", "ME": "MNE", "MK": "MKD", "AL": "ALB", "GR": "GRC",
    "BG": "BGR", "RO": "ROU", "MD": "MDA", "UA": "UKR", "BY": "BLR", "LT": "LTU",
    "LV": "LVA", "EE": "EST", "RU": "RUS", "AD": "AND", "MC": "MCO", "SM": "SMR",
    "VA": "VAT", "LI": "LIE",
    
    # Северная Америка
    "US": "USA", "CA": "CAN", "MX": "MEX", "GT": "GTM", "BZ": "BLZ", "SV": "SLV",
    "HN": "HND", "NI": "NIC", "CR": "CRI", "PA": "PAN", "CU": "CUB", "JM": "JAM",
    "HT": "HTI", "DO": "DOM", "TT": "TTO", "BB": "BRB", "GD": "GRD", "VC": "VCT",
    "LC": "LCA", "DM": "DMA", "AG": "ATG", "KN": "KNA", "BS": "BHS",
    
    # Южная Америка
    "BR": "BRA", "AR": "ARG", "CL": "CHL", "PE": "PER", "CO": "COL", "VE": "VEN",
    "EC": "ECU", "BO": "BOL", "PY": "PRY", "UY": "URY", "GY": "GUY", "SR": "SUR",
    "GF": "GUF", "FK": "FLK",
    
    # Африка
    "ZA": "ZAF", "EG": "EGY", "NG": "NGA", "KE": "KEN", "ET": "ETH", "GH": "GHA",
    "UG": "UGA", "TZ": "TZA", "MZ": "MOZ", "MG": "MDG", "CM": "CMR", "CI": "CIV",
    "NE": "NER", "BF": "BFA", "ML": "MLI", "MW": "MWI", "ZM": "ZMB", "ZW": "ZWE",
    "BW": "BWA", "NA": "NAM", "SZ": "SWZ", "LS": "LSO", "MU": "MUS", "SC": "SYC",
    "MR": "MRT", "SN": "SEN", "GM": "GMB", "GW": "GNB", "GN": "GIN", "SL": "SLE",
    "LR": "LBR", "TG": "TGO", "BJ": "BEN", "CV": "CPV", "ST": "STP", "GQ": "GNQ",
    "GA": "GAB", "CG": "COG", "CD": "COD", "CF": "CAF", "TD": "TCD", "LY": "LBY",
    "TN": "TUN", "DZ": "DZA", "MA": "MAR", "EH": "ESH", "SD": "SDN", "SS": "SSD",
    "ER": "ERI", "DJ": "DJI", "SO": "SOM", "RW": "RWA", "BI": "BDI", "KM": "COM",
    "AO": "AGO",
    
    # Океания
    "AU": "AUS", "NZ": "NZL", "FJ": "FJI", "PG": "PNG", "SB": "SLB", "NC": "NCL",
    "PF": "PYF", "VU": "VUT", "WS": "WSM", "TO": "TON", "TV": "TUV", "KI": "KIR",
    "NR": "NRU", "PW": "PLW", "FM": "FSM", "MH": "MHL", "CK": "COK", "NU": "NIU",
    "TK": "TKL", "WF": "WLF", "AS": "ASM", "GU": "GUM", "MP": "MNP",
    
    # Антарктида
    "AQ": "ATA"
}

# Отображение типов сообщений RTCM на несущие (также включает информацию о созвездиях)
CARRIER_INFO = {
    # GPS (1070-1077)
    (1070, 1070): ("GPS", "L1"),
    (1071, 1071): ("GPS", "L1+L2"),
    (1072, 1072): ("GPS", "L2"),
    (1073, 1073): ("GPS", "L1+C1"),
    (1074, 1074): ("GPS", "L5"),
    (1075, 1075): ("GPS", "L1+L5"),
    (1076, 1076): ("GPS", "L2+L5"),
    (1077, 1077): ("GPS", "L1+L2+L5"),
    
    # GLONASS (1080-1087)
    (1080, 1080): ("GLO", "G1"),
    (1081, 1081): ("GLO", "G1+G2"),
    (1082, 1082): ("GLO", "G2"),
    (1083, 1083): ("GLO", "G1+C1"),
    (1084, 1084): ("GLO", "G3"),
    (1085, 1085): ("GLO", "G1+G3"),
    (1086, 1086): ("GLO", "G2+G3"),
    (1087, 1087): ("GLO", "G1+G2+G3"),
    
    # Галилео (1090-1097)
    (1090, 1090): ("GAL", "E1"),
    (1091, 1091): ("GAL", "E1+E5b"),
    (1092, 1092): ("GAL", "E5b"),
    (1093, 1093): ("GAL", "E1+C1"),
    (1094, 1094): ("GAL", "E5a"),
    (1095, 1095): ("GAL", "E1+E5a"),
    (1096, 1096): ("GAL", "E5b+E5a"),
    (1097, 1097): ("GAL", "E1+E5a+E5b"),
    
    # Японский QZSS (1100-1107)
    (1100, 1100): ("QZSS", "L1"),
    (1101, 1101): ("QZSS", "L1+L2"),
    (1102, 1102): ("QZSS", "L2"),
    (1103, 1103): ("QZSS", "L1+C1"),
    (1104, 1104): ("QZSS", "L5"),
    (1105, 1105): ("QZSS", "L1+L5"),
    (1106, 1106): ("QZSS", "L2+L5"),
    (1107, 1107): ("QZSS", "L1+L2+L5+LEX"),
    
    # Индийский IRNSS (1110-1117)
    (1110, 1110): ("IRNSS", "L5"),
    (1111, 1111): ("IRNSS", "L5+S"),
    (1112, 1112): ("IRNSS", "S"),
    (1113, 1113): ("IRNSS", "L5+C1"),
    (1114, 1114): ("IRNSS", "L1"),
    (1115, 1115): ("IRNSS", "L1+L5"),
    (1116, 1116): ("IRNSS", "L1+S"),
    (1117, 1117): ("IRNSS", "L1+L5+S"),
    
    # Бэйдоу BDS (1120-1127)
    (1120, 1120): ("BDS", "B1I"),
    (1121, 1121): ("BDS", "B1I+B3I"),
    (1122, 1122): ("BDS", "B3I"),
    (1123, 1123): ("BDS", "B1I+B2I"),
    (1124, 1124): ("BDS", "B2I"),
    (1125, 1125): ("BDS", "B1I+B2I"),
    (1126, 1126): ("BDS", "B2I+B3I"),
    (1127, 1127): ("BDS", "B1I+B2I+B3I"),
    
    # SBAS (1040-1047)
    (1040, 1040): ("SBAS", "L1"),
    (1041, 1041): ("SBAS", "L1+L5"),
    (1042, 1042): ("SBAS", "L5"),
    (1043, 1043): ("SBAS", "L1+C1"),
    (1044, 1044): ("SBAS", "L1+L2"),
    (1045, 1045): ("SBAS", "L2+L5"),
    (1046, 1046): ("SBAS", "L2"),
    (1047, 1047): ("SBAS", "L1+L2+L5")
}

# Перечисление типов данных
class DataType:
    MSM_SATELLITE = "msm_satellite"  # Данные сигналов спутников MSM
    GEOGRAPHY = "geography"          # Данные географического местоположения
    DEVICE_INFO = "device_info"      # Информация об устройстве
    BITRATE = "bitrate"              # Данные битрейта
    MESSAGE_STATS = "message_stats"  # Статистика сообщений


class RTCMParserThread(threading.Thread):
    """Поток парсинга данных RTCM"""
    
    def __init__(self, mount_name: str, mode: str = "str_fix", 
                 duration: int = 30, push_callback: Optional[Callable[[Dict], None]] = None):
        super().__init__(daemon=True)
        self.mount_name = mount_name
        self.mode = mode  # str_fix: Исправление STR; realtime_web: Визуализация для Web
        self.duration = duration  # Действительно только для режима STR
        self.push_callback = push_callback  # Обратный вызов для отправки данных
        
        # Управление потоком
        self.running = threading.Event()
        self.running.set()
        
        # Хранилище результатов парсинга
        self.result: Dict = {
            "mount": mount_name,
            "location": None,  # Информация о местоположении: ecef, широта/долгота и т.д.
            "device": None,    # Информация об устройстве: приемник, антенна и т.д.
            "bitrate": None,   # Битрейт
            "message_stats": {
                "types": defaultdict(int),  # Подсчет типов сообщений
                "gnss": set(),              # Множество созвездий
                "carriers": set(),          # Множество несущих
                "frequency": {}             # Частота сообщений
            }
        }
        self.result_lock = threading.Lock()
        
        # Канал связи
        self.pipe_r, self.pipe_w = socket.socketpair()
        self.pipe_r.settimeout(5.0)  # Увеличение таймаута для уменьшения ошибок из-за сетевых задержек
        
        # Переменные, связанные со статистикой
        self.stats_start_time = time.time()
        self.total_bytes = 0  # Общее количество байт (для расчета битрейта)
        self.last_stats_time = time.time()  # Время последней статистики
        self.stats_delay = 5.0  # Задержка начала статистики на 5 секунд, чтобы избежать влияния исторических данных буфера
        self.stats_enabled = False  # Включена ли статистика
        
        log_debug(f"Инициализация RTCMParserThread для точки монтирования {mount_name}, режим: {mode}")

    def run(self):
        """Основная логика потока"""
        log_info(f"Запуск потока парсинга для точки монтирования {self.mount_name}, режим: {self.mode}")
        try:
            # Регистрация подписки на данные
            forwarder.register_subscriber(self.mount_name, self.pipe_w)
            stream = self.pipe_r.makefile("rb")
            reader = RTCMReader(stream)
            self.start_time = time.time()

            while self.running.is_set():
                # Проверка таймаута для режима STR
                if self.mode == "str_fix" and time.time() - self.start_time > self.duration:
                    log_info(f"Поток парсинга RTCM завершен для точки монтирования {self.mount_name}, длительность: {self.duration}s")
                    break

                # Чтение и парсинг сообщений
                try:
                    raw, msg = next(reader)
                    if not msg:
                        continue
                    
                    # Проверка необходимости включения статистики (включение через 5 секунд)
                    current_time = time.time()
                    if not self.stats_enabled and current_time - self.start_time >= self.stats_delay:
                        self.stats_enabled = True
                        self.stats_start_time = current_time  # Сброс времени начала статистики
                        self.last_stats_time = current_time
                        self.total_bytes = 0  # Сброс счетчика байт
                        log_info(f"Начало статистики битрейта для точки монтирования {self.mount_name} - включение после задержки {self.stats_delay} секунд")
                    
                    # Обновление общего количества байт (только после включения статистики)
                    if self.stats_enabled:
                        self.total_bytes += len(raw)
                    
                    # Парсинг типа сообщения
                    msg_id = self._get_msg_id(msg)
                    if msg_id:
                        # Отладка: запись специальных типов сообщений
                        # if msg_id in (1005, 1006, 1033):
                        #     log_info(f"[Парсинг RTCM] Получено сообщение типа {msg_id} - Точка монтирования: {self.mount_name}")
                        
                        # Общее обновление статистики
                        self._update_message_stats(msg_id)
                        
                        # Распределение обработки по режимам
                        if self.mode == "str_fix":
                            self._process_str_fix(msg, msg_id, raw)
                        else:  # realtime_web
                            self._process_realtime_web(msg, msg_id, raw)
                    
                    # Обновление статистики каждые 10 секунд (только после включения статистики)
                    if self.stats_enabled and time.time() - self.last_stats_time >= 10:
                        self._calculate_bitrate()
                        self._calculate_message_frequency()
                        self._generate_gnss_carrier_info()

                except StopIteration:
                    break
                except socket.timeout:
                    continue
                except Exception as e:
                    # Специальная обработка ошибок, связанных с таймаутом, чтобы избежать перегрузки логов
                    error_msg = str(e)
                    if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
                        # Ошибки таймаута только записываются в отладочную информацию, не в логи ошибок
                        continue
                    else:
                        log_error(f"Ошибка парсинга сообщения для точки монтирования {self.mount_name}: {error_msg}")

        except Exception as e:
            log_error(f"Исключение в потоке парсинга для точки монтирования {self.mount_name}: {str(e)}")
        finally:
            # Очистка ресурсов
            forwarder.unregister_subscriber(self.mount_name, self.pipe_w)
            self.pipe_r.close()
            self.pipe_w.close()
            log_info(f"Поток парсинга остановлен для точки монтирования {self.mount_name}")

    def _get_msg_id(self, msg: RTCMMessage) -> Optional[int]:
        """Получение ID сообщения (безопасная обработка)"""
        try:
            return int(getattr(msg, 'identity', -1))
        except (ValueError, TypeError):
            return None

    # -------------------------- Функции обработки информации о местоположении --------------------------
    def _process_location_message(self, msg: RTCMMessage, msg_id: int) -> None:
        """Обработка сообщений 1005/1006, извлечение информации о местоположении и ID базовой станции"""
        if msg_id not in (1005, 1006):
            return

        # print(f"[Сообщения 1005/1006] Получено сообщение о местоположении: {msg_id}")
            # print(f"[Сообщения 1005/1006] Объект сообщения: {msg}")
            # print(f"[Сообщения 1005/1006] Атрибуты сообщения: {dir(msg)}")

        # Извлечение ID базовой станции
        station_id = getattr(msg, "DF003", None) if hasattr(msg, "DF003") else None
        # print(f"[Сообщения 1005/1006] ID базовой станции: {station_id}")
        
        # Извлечение координат ECEF и преобразование в широту/долготу
        try:
            x, y, z = msg.DF025, msg.DF026, msg.DF027
            # print(f"[Сообщения 1005/1006] Координаты ECEF: X={x}, Y={y}, Z={z}")
            
            transformer = Transformer.from_crs("epsg:4978", "epsg:4326", always_xy=True)
            lon, lat, height = transformer.transform(x, y, z)
            # print(f"[Сообщения 1005/1006] Преобразованные координаты: Долгота={lon}, Широта={lat}, Высота={height}")
            
            # Обратная геокодировка - получение полной информации напрямую, без преобразований отображения
            country_code, country_name, city = self._reverse_geocode(lat, lon)
            # Для совместимости с исправлением STR все еще требуется 3-символьный код страны
            country_3code = COUNTRY_CODE_MAP.get(country_code, country_code) if country_code else None
            # print(f"[Сообщения 1005/1006] Геокодирование: Код страны={country_code}, Название страны={country_name}, Город={city}")

            # Формирование результата - оптимизированная структура данных, включающая оригинальные XYZ и ID базовой станции
            location_data = {
                "mount": self.mount_name,
                "mount_name": self.mount_name,  # Поле совместимости для фронтенда
                "station_id": station_id,
                "id": station_id,  # Поле совместимости для фронтенда
                "name": self.mount_name,  # Поле совместимости для фронтенда
                # Оригинальные координаты ECEF
                "ecef": {"x": x, "y": y, "z": z},
                "x": x,  # Поле совместимости для фронтенда
                "y": y,  # Поле совместимости для фронтенда
                "z": z,  # Поле совместимости для фронтенда
                # Преобразованные географические координаты
                "lat": round(lat, 8),
                "latitude": round(lat, 8),  # Поле совместимости для фронтенда
                "lon": round(lon, 8),
                "longitude": round(lon, 8),  # Поле совместимости для фронтенда
                "height": round(height, 3),
                # Информация о географическом местоположении
                "country": country_3code,  # 3-символьный код страны (для исправления STR)
                "country_code": country_code,  # 2-символьный код страны
                "country_name": country_name,  # Полное название страны (используется фронтендом напрямую)
                "city": city
            }

            # print(f"[Сообщения 1005/1006] Итоговые данные: {location_data}")

            # Обновление результата и отправка
            with self.result_lock:
                self.result["location"] = location_data
            self._push_data(DataType.GEOGRAPHY, location_data)
            # print(f"[Сообщения 1005/1006] Данные отправлены на фронтенд")

        except Exception as e:
            # print(f"[Сообщения 1005/1006] Ошибка парсинга информации о местоположении: {str(e)}")
            log_error(f"Ошибка парсинга информации о местоположении: {str(e)}")

    def _reverse_geocode(self, lat: float, lon: float, min_population: int = 10000) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Обратный запрос кода страны, полного названия страны и названия города по координатам
        
        Параметры:
            lat: Широта
            lon: Долгота
            min_population: Минимальный порог населения (фильтрация маленьких городов, по умолчанию 10000)
        
        Возвращает:
            Tuple[Код страны (2 символа), Полное название страны, Название города], при неудаче возвращает (None, None, None)
        """
        try:
            import reverse_geocode  # Внимание: это библиотека reverse_geocode, не reverse_geocoder
            # Для одной координаты используется метод get вместо search
            result = reverse_geocode.get((lat, lon), min_population=min_population)
            if not result:
                log_warning(f"Геокодирование не дало результатов: lat={lat}, lon={lon}")
                return None, None, None
            
            # Извлечение необходимых полей (обработка возможных отсутствующих значений)
            country_code = result.get("country_code")
            country_name = result.get("country")
            city_name = result.get("city")
            return country_code, country_name, city_name
        except ImportError:
            log_warning("Библиотека reverse_geocode не установлена, пожалуйста, выполните: pip install reverse-geocode")
            return None, None, None
        except Exception as e:
            log_warning(f"Ошибка при обратном геокодировании: {str(e)}")
            return None, None, None

    # -------------------------- Функции обработки сообщений 1033 --------------------------
    def _process_device_info(self, msg: RTCMMessage, msg_id: int) -> None:
        """Обработка сообщений 1033, извлечение информации об устройстве"""
        if msg_id != 1033:
            return

        # print(f"[Сообщения 1033] Получено сообщение с информацией об устройстве: {msg_id}")
        # print(f"[Сообщения 1033] Объект сообщения: {msg}")
        # print(f"[Сообщения 1033] Атрибуты сообщения: {dir(msg)}")

        try:
            # Извлечение информации об устройстве (согласно стандартным полям RTCM 1033)
            # Поля сообщения 1033 сегментированы, требуется склейка
            
            # Извлечение описания антенны (поля DF030_xx)
            antenna_parts = []
            # print(f"[Сообщения 1033] Начало парсинга полей описания антенны...")
            for i in range(1, 21):  # DF030_01 до DF030_20
                field_name = f"DF030_{i:02d}"
                if hasattr(msg, field_name):
                    part = getattr(msg, field_name)
                    # print(f"[Сообщения 1033] {field_name}: {part} (тип: {type(part)})")
                    if part and part != 0:  # Пропуск пустых значений
                        antenna_parts.append(chr(part) if isinstance(part, int) and 0 < part < 256 else str(part))
            antenna = ''.join(antenna_parts).strip() if antenna_parts else None
            # print(f"[Сообщения 1033] Результат склейки описания антенны: '{antenna}'")
            
            # Извлечение типа приемника (поля DF228_xx)
            receiver_parts = []
            # print(f"[Сообщения 1033] Начало парсинга полей типа приемника...")
            for i in range(1, 31):  # DF228_01 до DF228_30
                field_name = f"DF228_{i:02d}"
                if hasattr(msg, field_name):
                    part = getattr(msg, field_name)
                    # print(f"[Сообщения 1033] {field_name}: {part} (тип: {type(part)})")
                    if part and part != 0:  # Пропуск пустых значений
                        receiver_parts.append(chr(part) if isinstance(part, int) and 0 < part < 256 else str(part))
            receiver = ''.join(receiver_parts).strip() if receiver_parts else None
            # print(f"[Сообщения 1033] Результат склейки типа приемника: '{receiver}'")
            
            # Извлечение версии прошивки (поля DF230_xx)
            firmware_parts = []
            # print(f"[Сообщения 1033] Начало парсинга полей версии прошивки...")
            for i in range(1, 21):  # DF230_01 до DF230_20
                field_name = f"DF230_{i:02d}"
                if hasattr(msg, field_name):
                    part = getattr(msg, field_name)
                    # print(f"[Сообщения 1033] {field_name}: {part} (тип: {type(part)})")
                    if part and part != 0:  # Пропуск пустых значений
                        firmware_parts.append(chr(part) if isinstance(part, int) and 0 < part < 256 else str(part))
            firmware = ''.join(firmware_parts).strip() if firmware_parts else None
            # print(f"[Сообщения 1033] Результат склейки версии прошивки: '{firmware}'")
            
            # Извлечение серийного номера антенны (поле DF033 или другие возможные поля)
            antenna_serial = getattr(msg, "DF033", None)
            # print(f"[Сообщения 1033] DF033 (серийный номер антенны): {antenna_serial}")
            if not antenna_serial:
                # Попытка других возможных полей серийного номера
                antenna_serial = getattr(msg, "DF032", None)
                # print(f"[Сообщения 1033] DF032 (резервный серийный номер): {antenna_serial}")
            
            # print(f"[Сообщения 1033] Приемник: {receiver}")
            # print(f"[Сообщения 1033] Прошивка: {firmware}")
            # print(f"[Сообщения 1033] Антенна: {antenna}")
            # print(f"[Сообщения 1033] Серийный номер антенны: {antenna_serial}")
            
            # Вывод всех доступных атрибутов для отладки
            # print(f"[Сообщения 1033] Все атрибуты: {[attr for attr in dir(msg) if not attr.startswith('_')]}")
            
            device_data = {
                "mount": self.mount_name,
                "receiver": receiver,
                "firmware": firmware,
                "antenna": antenna,
                "antenna_firmware": antenna_serial
            }

            # print(f"[Сообщения 1033] Итоговые данные: {device_data}")

            # Обновление результата и отправка
            with self.result_lock:
                self.result["device"] = device_data
            self._push_data(DataType.DEVICE_INFO, device_data)
            # print(f"[Сообщения 1033] Данные отправлены на фронтенд")

        except Exception as e:
            # print(f"[Сообщения 1033] Ошибка парсинга информации об устройстве: {str(e)}")
            log_error(f"Ошибка парсинга информации об устройстве: {str(e)}")

    # -------------------------- Функции статистики битрейта --------------------------
    def _calculate_bitrate(self) -> None:
        """Расчет битрейта (реальные данные после задержки запуска)"""
        if not self.stats_enabled:
            return
            
        current_time = time.time()
        elapsed = current_time - self.last_stats_time
        if elapsed < 1:  # Избегание деления на ноль
            return

        bitrate = (self.total_bytes * 8) / elapsed  # Преобразование байтов в биты
        total_elapsed = current_time - self.stats_start_time  # Общее время статистики
        
        with self.result_lock:
            self.result["bitrate"] = round(bitrate, 2)
        
        log_debug(f"Статистика битрейта для точки монтирования {self.mount_name} - Период: {elapsed:.1f}с, Байты: {self.total_bytes}, Битрейт: {bitrate:.2f} бит/с, Общее время статистики: {total_elapsed:.1f}с")
        
        self._push_data(DataType.BITRATE, {
            "mount": self.mount_name,
            "bitrate": round(bitrate, 2),
            "period": f"{elapsed:.1f}s"
        })
        log_debug(f"Обновление битрейта для точки монтирования {self.mount_name}: {bitrate:.2f} бит/с, Период: {elapsed:.1f}с, Количество байт: {self.total_bytes}")
        
        # Сброс счетчика байт и времени статистики, чтобы избежать завышения битрейта из-за накопления
        self.total_bytes = 0
        self.last_stats_time = current_time

    # -------------------------- Функции статистики типов сообщений --------------------------
    def _update_message_stats(self, msg_id: int) -> None:
        """Обновление подсчета типов сообщений, информации о созвездиях и несущих"""
        with self.result_lock:
            # Подсчет типов сообщений
            self.result["message_stats"]["types"][msg_id] += 1
            
            # Одновременное получение информации о созвездиях и несущих из CARRIER_INFO
            for (start, end), (gnss, carrier) in CARRIER_INFO.items():
                if start <= msg_id <= end:
                    # Добавление информации о созвездии
                    self.result["message_stats"]["gnss"].add(gnss)
                    
                    # Разделение комбинированных несущих (например, L1+L2 разделяется на L1 и L2)
                    for c in carrier.split("+"):
                        self.result["message_stats"]["carriers"].add(c)
                    break

    def _calculate_message_frequency(self) -> None:
        """Расчет частоты типов сообщений за 10 секунд"""
        with self.result_lock:
            types = self.result["message_stats"]["types"]
            frequency = {}
            for msg_id, count in types.items():
                # Округление частоты, минимум 1
                freq = max(1, round(count / 10))  # Период статистики 10 секунд
                frequency[msg_id] = freq
            self.result["message_stats"]["frequency"] = frequency

    def _generate_gnss_carrier_info(self) -> None:
        """Генерация и отправка комбинированных строк созвездий и несущих"""
        with self.result_lock:
            gnss_str = "+".join(sorted(self.result["message_stats"]["gnss"])) or "N/A"
            carrier_str = "+".join(sorted(self.result["message_stats"]["carriers"])) or "N/A"
            types_str = ",".join([f"{k}({v})" for k, v in self.result["message_stats"]["frequency"].items()])

            stats_data = {
                "mount": self.mount_name,
                "message_types": types_str,
                "gnss": gnss_str,
                "carriers": carrier_str
            }

        self._push_data(DataType.MESSAGE_STATS, stats_data)
        log_debug(f"Обновление статистической информации для точки монтирования {self.mount_name}: {stats_data}")

    # -------------------------- Функции обработки сообщений MSM --------------------------
    def _process_msm_messages(self, msg: RTCMMessage, msg_id: int) -> None:
        """Обработка сообщений MSM, извлечение силы сигнала спутников"""
        # Проверка, является ли сообщение MSM (диапазон 1040-1127)
        if not (1040 <= msg_id <= 1127):
            return

        try:
            # Парсинг сообщения MSM
            msm_result = parse_msm(msg)
            if not msm_result:
                return
            
            # parse_msm возвращает кортеж (meta, msmsats, msmcells)
            meta, msmsats, msmcells = msm_result
            
            if not msmcells:
                return
            
            # Построение данных сигналов спутников
            sats_data = []
            for cell in msmcells:
                # Извлечение данных силы сигнала
                cnr = cell.get('DF408') or cell.get('DF403') or cell.get('DF405') or 0
                if cnr > 0:  # Обработка только валидных данных силы сигнала
                    sat_data = {
                        "id": cell.get('CELLPRN', 0),
                        "signal_type": cell.get('CELLSIG', 0),
                        "snr": cnr,
                        "lock_time": cell.get('DF407', 0),
                        "pseudorange": cell.get('DF400', 0),
                        "carrier_phase": cell.get('DF401', 0) or cell.get('DF406', 0),
                        "doppler": cell.get('DF404', 0)
                    }
                    sats_data.append(sat_data)
            
            if sats_data:
                # Отправка данных сигналов спутников MSM
                self._push_data(DataType.MSM_SATELLITE, {
                    "gnss": meta.get('gnss', 'UNKNOWN'),
                    "msg_type": msg_id,
                    "station_id": meta.get('station', 0),
                    "epoch": meta.get('epoch', 0),
                    "total_sats": len(sats_data),
                    "sats": sats_data
                })
                log_debug(f"Отправка данных сигналов спутников MSM: {meta.get('gnss')} сообщение {msg_id}, {len(sats_data)} спутников")

        except Exception as e:
            log_debug(f"Парсинг сообщений MSM пропущен: {str(e)}")  # Не критическая ошибка, только отладочный лог

    # -------------------------- Распределение обработки по режимам --------------------------
    def _process_str_fix(self, msg: RTCMMessage, msg_id: int, raw: bytes) -> None:
        """Логика обработки режима исправления STR"""
        # Обработка только необходимых типов сообщений
        if msg_id in (1005, 1006):
            self._process_location_message(msg, msg_id)
        elif msg_id == 1033:
            self._process_device_info(msg, msg_id)

    def _process_realtime_web(self, msg: RTCMMessage, msg_id: int, raw: bytes) -> None:
        """Логика обработки режима Web в реальном времени (обработка всех типов сообщений)"""
        # print(f"[Режим Web] Обработка ID сообщения: {msg_id}")
        
        # Обработка информации о местоположении (1005/1006)
        if msg_id in (1005, 1006):
            # print(f"[Режим Web] Вызов функции обработки сообщений о местоположении")
            self._process_location_message(msg, msg_id)
        
        # Обработка информации об устройстве (1033)
        elif msg_id == 1033:
            # print(f"[Режим Web] Вызов функции обработки информации об устройстве")
            self._process_device_info(msg, msg_id)
        
        # Обработка сообщений MSM
        elif msg_id in range(1070, 1130):
            # Сообщения MSM не выводят подробную информацию, чтобы избежать перегрузки экрана
            self._process_msm_messages(msg, msg_id)
        else:
            self._process_location_message(msg, msg_id)
            self._process_device_info(msg, msg_id)
            self._process_msm_messages(msg, msg_id)

    # -------------------------- Отправка данных --------------------------
    def _push_data(self, data_type: str, data: Dict) -> None:
        """Отправка данных через функцию обратного вызова"""
        if self.push_callback:
            try:
                self.push_callback({
                    "mount_name": self.mount_name,  # Добавление поля mount_name
                    "data_type": data_type,  # Изменено на data_type для согласованности
                    "timestamp": time.time(),
                    **data  # Разворачивание содержимого словаря data на верхний уровень
                })
            except Exception as e:
                log_error(f"Ошибка при отправке данных: {str(e)}")

    # -------------------------- Управление потоком --------------------------
    def stop(self) -> None:
        """Остановка потока парсинга"""
        self.running.clear()
        self.join(timeout=5)
        log_info(f"Поток парсинга для точки монтирования {self.mount_name} закрыт")


# -------------------------- Интерфейсы парсинга --------------------------
def start_str_fix_parser(mount_name: str, duration: int = 30, 
                         callback: Optional[Callable[[Dict], None]] = None) -> RTCMParserThread:
    """Запуск потока парсинга режима исправления STR"""
    parser = RTCMParserThread(mount_name, mode="str_fix", duration=duration, push_callback=callback)
    parser.start()
    return parser


def start_web_parser(mount_name: str, callback: Optional[Callable[[Dict], None]] = None) -> RTCMParserThread:
    """Запуск потока парсинга Web в реальном времени"""
    parser = RTCMParserThread(mount_name, mode="realtime_web", push_callback=callback)
    parser.start()
    return parser
