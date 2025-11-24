#!/usr/bin/env python3
"""
web.py - Модуль веб-управления
Функции: Предоставление интерфейсов для фронтенда, отображение информации о точках монтирования в реальном времени, поддержка просмотра и запроса данных парсинга точек монтирования
"""

import time
import json
import logging
import psutil
import re
from datetime import datetime
from functools import wraps
from threading import Thread

from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, send_from_directory
# from flask_cors import CORS  # Удалено, функциональность CORS не требуется
import os
from flask_socketio import SocketIO, emit, join_room

from .database import DatabaseManager
from . import config
from . import logger
from .logger import log_debug, log_info, log_warning, log_error, log_critical, log_web_request, log_system_event
from . import connection
from . import forwarder
from .rtcm2_manager import parser_manager as rtcm_manager

# Глобальная ссылка на экземпляр сервера
server_instance = None

def set_server_instance(server):
    """Установка экземпляра сервера"""
    global server_instance
    server_instance = server

def get_server_instance():
    """Получение экземпляра сервера"""
    return server_instance

# Получение регистратора логов
# web_logger = logger.get_logger('main')  # Переключились на прямые функции log_

class WebManager:
    """Веб-менеджер"""
    
    def __init__(self, db_manager, data_forwarder, start_time):
        self.db_manager = db_manager
        self.data_forwarder = data_forwarder
        self.start_time = start_time
        
        # Создание экземпляра менеджера подключений
        global rtcm
        rtcm = connection.ConnectionManager()
        
        # Директории шаблонов и статических файлов
        self.template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
        self.static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
        
        # Создание приложения Flask
        self.app = Flask(__name__, static_folder=self.static_dir, static_url_path='/static')
        self.app.secret_key = config.FLASK_SECRET_KEY
        
        # Настройка CORS - удалено, проект развернут в одном домене, функциональность CORS не требуется
        # CORS(self.app, origins="*" if config.DEBUG else config.WEBSOCKET_CONFIG['cors_allowed_origins'])
        
        # Создание экземпляра SocketIO
        # Явное использование режима threading на Windows для избежания проблем совместимости с eventlet
        # Удалена конфигурация CORS, проект развернут в одном домене, межсайтовая поддержка не требуется
        self.socketio = SocketIO(
            self.app, 
            async_mode='threading',  # Явное указание режима threading
            # cors_allowed_origins="*" if config.DEBUG else config.WEBSOCKET_CONFIG['cors_allowed_origins'],  # CORS удалено
            ping_timeout=config.WEBSOCKET_CONFIG['ping_timeout'],
            ping_interval=config.WEBSOCKET_CONFIG['ping_interval']
        )
        
        # Регистрация маршрутов
        self._register_routes()
        self._register_socketio_events()
        
        # Поток отправки данных в реальном времени
        self.push_thread = None
        self.push_running = False
        
        # Установка ссылки на экземпляр web для logger, используется для отправки логов в реальном времени
        logger.set_web_instance(self)
    
    def _format_uptime_simple(self, uptime_seconds):
        """Форматирование времени работы (простая версия)"""
        try:
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            
            if days > 0:
                return f"{days} дн. {hours} ч. {minutes} мин."
            elif hours > 0:
                return f"{hours} ч. {minutes} мин."
            else:
                return f"{minutes} мин."
        except:
            return "0 мин."
    
    def _validate_alphanumeric(self, value, field_name):
        """Проверка, содержит ли ввод только английские буквы, цифры, подчеркивания и дефисы"""
        if not value:
            return False, f"{field_name} не может быть пустым"
        
        # Разрешены английские буквы, цифры, подчеркивания и дефисы
        if not re.match(r'^[a-zA-Z0-9_-]+$', value):
            return False, f"{field_name} может содержать только английские буквы, цифры, подчеркивания и дефисы"
        
        return True, ""
    
    def _load_template(self, template_name, **kwargs):
        """Загрузка внешнего файла шаблона"""
        template_path = os.path.join(self.template_dir, template_name)
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
            return render_template_string(template_content, **kwargs)
        except FileNotFoundError:
            log_error(f"Файл шаблона не найден: {template_path}")
            return f"<h1>Файл шаблона не найден: {template_name}</h1>"
        except Exception as e:
            log_error(f"Ошибка при загрузке файла шаблона: {e}")
            return f"<h1>Ошибка загрузки шаблона: {str(e)}</h1>"
    
    def _register_routes(self):
        """Регистрация маршрутов Flask"""
        
        @self.app.route('/static/<path:filename>')
        def static_files(filename):
            """Служба статических файлов"""
            static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
            return send_from_directory(static_dir, filename)
        
        @self.app.route('/')
        def index():
            """Главная страница - SPA приложение"""
            # Получение информации о конфигурации
            app_name = config.get_config_value('app', 'name', '2RTK NTRIP Caster')
            app_version = config.get_config_value('app', 'version', config.APP_VERSION)
            current_year = datetime.now().year
            
            return self._load_template('spa.html', 
                                     app_name=app_name,
                                     app_version=app_version,
                                     current_year=current_year,
                                     contact_email='i@jia.by',
                                     website_url='2RTK.COM')
        
        @self.app.route('/classic')
        @self.require_login
        def classic_index():
            """Классическая главная страница - состояние системы и информация о точках монтирования"""
            # Получение системной информации
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            uptime = time.time() - self.start_time
            
            # Получение запущенных точек монтирования
            running_mounts = self.db_manager.get_running_mounts()
            
            # Получение онлайн пользователей
            online_users = connection.get_connection_manager().get_online_users()
            
            # Получение данных парсинга RTCM
            parsed_data = connection.get_statistics().get('mounts', {})
            
            return self._load_template('index.html', 
                                        cpu_percent=cpu_percent,
                                        memory_percent=memory.percent,
                                        memory_used=memory.used // (1024*1024),
                                        memory_total=memory.total // (1024*1024),
                                        uptime=self._format_uptime(uptime),
                                        running_mounts=running_mounts,
                                        online_users=online_users,
                                        parsed_data=parsed_data)
        
        @self.app.route('/login', methods=['GET', 'POST'])
        def login():
            """Страница входа"""
            if request.method == 'POST':
                # Валидация формы
                username = request.form.get('username', '').strip()
                password = request.form.get('password', '').strip()
                
                # Предотвращение отправки пустых полей
                if not username or not password:
                    return self._load_template('login.html', error="Имя пользователя и пароль не могут быть пустыми")
                
                # Проверка длины
                if len(username) < 2 or len(username) > 50:
                    return self._load_template('login.html', error="Длина имени пользователя должна быть от 2 до 50 символов")
                
                if len(password) < 6 or len(password) > 100:
                    return self._load_template('login.html', error="Длина пароля должна быть от 6 до 100 символов")
                
                # Проверка символов имени пользователя
                username_valid, username_error = self._validate_alphanumeric(username, "Имя пользователя")
                if not username_valid:
                    return self._load_template('login.html', error=username_error)
                
                # Проверка символов пароля
                password_valid, password_error = self._validate_alphanumeric(password, "Пароль")
                if not password_valid:
                    return self._load_template('login.html', error=password_error)
                
                if self.db_manager.verify_admin(username, password):
                    session['admin_logged_in'] = True
                    session['admin_username'] = username
                    
                    # Проверка параметра перенаправления
                    redirect_page = request.args.get('redirect')
                    if redirect_page and redirect_page in ['users', 'mounts', 'settings']:
                        return redirect(f'/?page={redirect_page}')
                    
                    return redirect(url_for('index'))
                else:
                    return self._load_template('login.html', error="Неверное имя пользователя или пароль")
            
            return self._load_template('login.html')
        
        @self.app.route('/logout', methods=['GET', 'POST'])
        def logout():
            """Выход"""
            session.clear()
            if request.method == 'POST':
                return jsonify({'success': True})
            return redirect(url_for('login'))
        
        @self.app.route('/api/login', methods=['POST'])
        def api_login():
            """API входа"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'error': 'Ошибка формата данных запроса'}), 400
                
                username = data.get('username', '').strip()
                password = data.get('password', '').strip()
                
                # Предотвращение отправки пустых полей
                if not username or not password:
                    return jsonify({'error': 'Имя пользователя и пароль не могут быть пустыми'}), 400
                
                # Проверка длины
                if len(username) < 2 or len(username) > 50:
                    return jsonify({'error': 'Длина имени пользователя должна быть от 2 до 50 символов'}), 400
                
                if len(password) < 6 or len(password) > 100:
                    return jsonify({'error': 'Длина пароля должна быть от 6 до 100 символов'}), 400
                
                # Базовая проверка символов для предотвращения SQL-инъекций
                if any(char in username for char in ["'", '"', ';', '--', '/*', '*/', 'xp_']):
                    return jsonify({'error': 'Имя пользователя содержит недопустимые символы'}), 400
                
                if self.db_manager.verify_admin(username, password):
                    session['admin_logged_in'] = True
                    session['admin_username'] = username
                    return jsonify({
                        'success': True,
                        'message': 'Вход выполнен успешно',
                        'token': 'session_based'  # Использование session вместо JWT
                    })
                else:
                    return jsonify({'error': 'Неверное имя пользователя или пароль'}), 401
            except Exception as e:
                    log_error(f"Ошибка API входа: {e}")
                    return jsonify({'error': 'Ошибка входа'}), 500

        
        @self.app.route('/api/mount_info/<mount>')
        @self.require_login
        def mount_info(mount):
            """Получение информации о парсинге указанной точки монтирования и возврат на фронтенд"""
            parsed_data = rtcm_manager.get_parsed_mount_data(mount)
            statistics = rtcm_manager.get_mount_statistics(mount)
            
            if parsed_data:
                return jsonify({
                    'success': True,
                    'data': parsed_data,
                    'statistics': statistics
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Данные точки монтирования не существуют или не были распарсены'
                })
        

        
        @self.app.route('/api/system/restart', methods=['POST'])
        @self.require_login
        def restart_system():
            """API перезапуска программы"""
            try:
                import os
                import sys
                import threading
                
                def delayed_restart():
                    """Отложенный перезапуск программы"""
                    time.sleep(1)  # Дать время на ответ
                    log_info("Администратор запросил перезапуск программы")
                    os._exit(0)  # Принудительное завершение программы
                
                # Выполнение перезапуска в новом потоке
                restart_thread = threading.Thread(target=delayed_restart)
                restart_thread.daemon = True
                restart_thread.start()
                
                return jsonify({
                    'success': True,
                    'message': 'Команда перезапуска программы отправлена'
                })
                
            except Exception as e:
                    log_error(f"Ошибка при перезапуске программы: {e}")
                    return jsonify({
                        'success': False,
                        'error': str(e)
                    }), 500
        

        
        @self.app.route('/api/mount/<mount_name>/realtime')
        @self.require_login
        def api_get_mount_realtime(mount_name):
            """Получение данных парсинга в реальном времени для указанной точки монтирования"""
            try:
                realtime_data = rtcm_manager.get_parsed_mount_data(mount_name, limit=10)
                if realtime_data is None:
                    return jsonify({'error': 'Mount not found'}), 404
                return jsonify(realtime_data)
            except Exception as e:
                    log_error(f"Ошибка при получении данных в реальном времени для точки монтирования {mount_name}: {e}")
                    return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/mount/initialize', methods=['POST'])
        @self.require_login
        def api_initialize_mount():
            """Инициализация точки монтирования"""
            try:
                data = request.get_json()
                mount_name = data.get('mount_name')
                if not mount_name:
                    return jsonify({'error': 'Mount name is required'}), 400
                
                connection.get_connection_manager().add_mount_connection(mount_name, '127.0.0.1', 'Web Interface')
                log_system_event(f"Точка монтирования {mount_name} успешно инициализирована")
                return jsonify({'success': True, 'message': f'Mount {mount_name} initialized'})
            except Exception as e:
                log_error(f"Ошибка при инициализации точки монтирования: {e}")
                return jsonify({'error': str(e)}), 500
        

        

        
        @self.app.route('/api/bypass/stop-all', methods=['POST'])
        @self.require_login
        def api_stop_all_bypass_parsing():
            """Остановка парсинга обхода для всех точек монтирования"""
            try:
                rtcm_manager.stop_realtime_parsing()
                log_system_event("Парсинг обхода для всех точек монтирования успешно остановлен")
                return jsonify({'success': True, 'message': 'All bypass parsing stopped'})
            except Exception as e:
                log_error(f"Ошибка при остановке парсинга обхода: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/mount/<mount_name>/simulate', methods=['POST'])
        @self.require_login
        def api_simulate_mount_data(mount_name):
            """Симуляция данных для точки монтирования"""
            try:
                # Функциональность симуляции данных временно недоступна
                log_system_event(f"Запрос на симуляцию данных для точки монтирования {mount_name} (функциональность временно недоступна)")
                log_system_event(f"Симуляция данных для точки монтирования {mount_name} успешно запущена")
                return jsonify({'success': True, 'message': f'Data simulation started for {mount_name}'})
            except Exception as e:
                log_error(f"Ошибка при симуляции данных точки монтирования: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/mount/<mount_name>/rtcm-parse/start', methods=['POST'])
        @self.require_login
        def api_start_rtcm_parsing(mount_name):
            """Запуск парсинга RTCM в реальном времени для указанной точки монтирования"""
            try:
                # print(f"[Backend API] Получен запрос на запуск парсинга RTCM - Точка монтирования: {mount_name}")
                
                # Внимание: больше не вызываем stop_realtime_parsing() вручную,
                # поскольку новый метод start_realtime_parsing уже имеет встроенную логику интеллектуальной очистки
                # print(f"[Backend API] Подготовка к запуску задачи парсинга, встроенная логика очистки автоматически обработает предыдущий поток парсинга")
                
                # Определение обратного вызова отправки: получение данных парсинга из rtcm.py и отправка на фронтенд
                def push_callback(parsed_data):
                    mount_name = parsed_data.get("mount_name", "N/A")
                    data_type = parsed_data.get("data_type", "N/A")
                    timestamp = parsed_data.get("timestamp", "N/A")
                    data_keys = list(parsed_data.keys()) if isinstance(parsed_data, dict) else "N/A"
                    
                    # print(f"\n[Отправка с бэкенда] Подготовка отправки данных на фронтенд:")
        # print(f"   Точка монтирования: {mount_name}")
        # print(f"   Тип данных: {data_type}")
        # print(f"   Временная метка: {timestamp}")
        # print(f"   Ключи данных: {data_keys}")
                    
                    # Подробный вывод данных различных типов
                    if data_type == 'msm_satellite':
                        # Отладочная информация MSM спутников закомментирована, чтобы избежать перегрузки вывода
                        # print(f"   Детали данных MSM спутников:")
                        # print(f"      Тип GNSS: {parsed_data.get('gnss', 'N/A')}")
                        # print(f"      Тип сообщения: {parsed_data.get('msg_type', 'N/A')}")
                        # print(f"      Уровень MSM: {parsed_data.get('msm_level', 'N/A')}")
                        # print(f"      Количество спутников: {parsed_data.get('total_sats', 'N/A')}")
                        # if 'sats' in parsed_data and isinstance(parsed_data['sats'], list):
                        #     print(f"      Первые 3 спутника:")
                        #     for i, sat in enumerate(parsed_data['sats'][:3]):
                        #         print(f"        Спутник{i+1}: PRN={sat.get('id', 'N/A')}, SNR={sat.get('snr', 'N/A')}, Сигнал={sat.get('signal_type', 'N/A')}")
                        #     if len(parsed_data['sats']) > 3:
                        #         print(f"        ... еще {len(parsed_data['sats']) - 3} спутников")
                        pass
                    elif data_type == 'geography':
                        # print(f"   Детали географических данных:")
                        # print(f"      ID базовой станции: {parsed_data.get('station_id', 'N/A')}")
                        # print(f"      Широта: {parsed_data.get('lat', 'N/A')}")
                        # print(f"      Долгота: {parsed_data.get('lon', 'N/A')}")
                        # print(f"      Высота: {parsed_data.get('height', 'N/A')}")
                        # print(f"      Страна: {parsed_data.get('country', 'N/A')}")
                        # print(f"      Город: {parsed_data.get('city', 'N/A')}")
                        pass
                    elif data_type == 'device_info':
                        # print(f"   Детали информации об устройстве:")
                        # print(f"      Приемник: {parsed_data.get('receiver', 'N/A')}")
                        # print(f"      Версия прошивки: {parsed_data.get('firmware', 'N/A')}")
                        # print(f"      Антенна: {parsed_data.get('antenna', 'N/A')}")
                        # print(f"      Прошивка антенны: {parsed_data.get('antenna_firmware', 'N/A')}")
                        pass
                    elif data_type == 'message_stats':
                        # print(f"   Детали статистики сообщений:")
                        # print(f"      Типы сообщений: {parsed_data.get('message_types', 'N/A')}")
                        # print(f"      Система GNSS: {parsed_data.get('gnss', 'N/A')}")
                        # print(f"      Несущие частоты: {parsed_data.get('carriers', 'N/A')}")
                        pass
                    
                    # Вывод полных данных (обрезанный вывод) - для MSM данных не выводится, чтобы избежать перегрузки
                    if data_type != 'msm_satellite':
                        data_str = str(parsed_data)
                        # print(f"   Полные данные: {data_str[:500]}{'...' if len(data_str) > 500 else ''}")
                    
                    # Убедиться, что данные содержат mount_name
                    if 'mount_name' not in parsed_data:
                        # print(f"[Отправка с бэкенда] Отправляемые данные не содержат поля mount_name")
                        log_warning("Отправляемые данные не содержат поля mount_name")
                        return
                        
                    # Отправка через SocketIO на фронтенд, событие 'rtcm_realtime_data'
                    if data_type != 'msm_satellite':
                        # print(f"[Отправка с бэкенда] Отправка данных через SocketIO на фронтенд - событие: rtcm_realtime_data")
                        pass
                    self.socketio.emit(
                        'rtcm_realtime_data',
                        parsed_data
                    )
                    if data_type != 'msm_satellite':
                        # print(f"[Отправка с бэкенда] Отправка данных завершена\n")
                        pass
                
                # Запуск новой задачи разбора, передача функции обратного вызова
                # print(f"[API бэкенда] Запуск новой задачи разбора - точка монтирования: {mount_name}")
                success = rtcm_manager.start_realtime_parsing(
                    mount_name=mount_name,
                    push_callback=push_callback  # Замена оригинального параметра self.socketio
                )
                if success:
                    # print(f" [API бэкенда] Разбор запущен успешно - точка монтирования: {mount_name}")
                    log_system_event(f"Парсинг RTCM в реальном времени для точки монтирования {mount_name} запущен")
                    return jsonify({'success': True, 'message': f'Real-time RTCM parsing started for {mount_name}'})
                else:
                    # print(f"[API бэкенда] Ошибка запуска разбора - точка монтирования: {mount_name} (возможно, офлайн)")
                    return jsonify({'error': 'Failed to start parsing - mount may be offline'}), 400
            except Exception as e:
                # print(f"[API бэкенда] Исключение при запуске разбора RTCM: {e}")
                log_error(f"Ошибка при запуске парсинга RTCM в реальном времени: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/mount/rtcm-parse/stop', methods=['POST'])
        @self.require_login
        def api_stop_rtcm_parsing():
            """Остановка всего разбора RTCM в реальном времени"""
            try:
                rtcm_manager.stop_realtime_parsing()
                log_system_event("Весь парсинг RTCM в реальном времени остановлен")
                return jsonify({'success': True, 'message': 'Real-time RTCM parsing stopped'})
            except Exception as e:
                log_error(f"Ошибка при остановке парсинга RTCM в реальном времени: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/mount/rtcm-parse/status', methods=['GET'])
        @self.require_login
        def api_get_rtcm_parsing_status():
            """Получение информации о состоянии парсера RTCM"""
            try:
                status = rtcm_manager.get_parser_status()
                return jsonify({
                    'success': True, 
                    'status': status,
                    'message': 'Parser status retrieved successfully'
                })
            except Exception as e:
                log_error(f"Ошибка при получении состояния парсера: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/mount/rtcm-parse/heartbeat', methods=['POST'])
        @self.require_login
        def api_rtcm_parsing_heartbeat():
            """Поддержание пульса парсинга RTCM в реальном времени"""
            try:
                data = request.get_json()
                mount_name = data.get('mount_name') if data else None
                
                if mount_name:
                    # Обновление временной метки пульса
                    rtcm_manager.update_parsing_heartbeat(mount_name)
                    return jsonify({'success': True, 'message': 'Heartbeat updated'})
                else:
                    return jsonify({'error': 'Mount name is required'}), 400
            except Exception as e:
                log_error(f"Ошибка при обновлении пульса парсинга: {e}")
                return jsonify({'error': str(e)}), 500
        


        
        @self.app.route('/alipay_qr')
        def alipay_qr():
            """QR-код Alipay"""
            return redirect(config.ALIPAY_QR_URL)
        
        @self.app.route('/wechat_qr')
        def wechat_qr():
            """QR-код WeChat"""
            return redirect(config.WECHAT_QR_URL)
        

        @self.app.route('/api/app_info')
        def api_app_info():
            """Получение информации о приложении"""
            try:
                return jsonify({
                    'name': config.APP_NAME,
                    'version': config.APP_VERSION,
                    'description': config.APP_DESCRIPTION,
                    'author': config.APP_AUTHOR,
                    'contact': config.APP_CONTACT,
                    'website': config.APP_WEBSITE
                })
            except Exception as e:
                log_error(f"Ошибка при получении информации о приложении: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/users', methods=['GET', 'POST'])
        @self.require_login
        def api_users():
            """API управления пользователями"""
            if request.method == 'GET':
                # Получение списка пользователей
                try:
                    users = self.db_manager.get_all_users()
                    
                    # Получение информации об онлайн пользователях
                    try:
                        online_users = connection.get_connection_manager().get_online_users()
                        online_usernames = list(online_users.keys())
                    except Exception as e:
                        log_error(f"Ошибка при получении онлайн пользователей: {e}")
                        online_usernames = []
                    
                    # Преобразование tuple в формат словаря и добавление статуса онлайн и количества подключений
                    user_list = []
                    for user in users:
                        username = user[1]
                        connection_count = connection.get_connection_manager().get_user_connection_count(username)
                        connect_time = connection.get_connection_manager().get_user_connect_time(username)
                        user_dict = {
                            'id': user[0],
                            'username': username,
                            'online': username in online_usernames,
                            'connection_count': connection_count,
                            'connect_time': connect_time or '-'  # Время подключения
                        }
                        user_list.append(user_dict)
                    
                    return jsonify(user_list)
                except Exception as e:
                    log_error(f"Ошибка при получении списка пользователей: {e}")
                    return jsonify({'error': str(e)}), 500
            
            elif request.method == 'POST':
                # Добавление пользователя
                try:
                    data = request.get_json()
                    if not data:
                        return jsonify({'error': 'Ошибка формата данных запроса'}), 400
                    
                    username = data.get('username', '').strip()
                    password = data.get('password', '').strip()
                    
                    # Валидация формы
                    if not username or not password:
                        return jsonify({'error': 'Имя пользователя и пароль не могут быть пустыми'}), 400
                    
                    # Проверка символов имени пользователя
                    username_valid, username_error = self._validate_alphanumeric(username, "Имя пользователя")
                    if not username_valid:
                        return jsonify({'error': username_error}), 400
                    
                    # Проверка символов пароля
                    password_valid, password_error = self._validate_alphanumeric(password, "Пароль")
                    if not password_valid:
                        return jsonify({'error': password_error}), 400
                    
                    elif len(username) < 2 or len(username) > 50:
                        return jsonify({'error': 'Длина имени пользователя должна быть от 2 до 50 символов'}), 400
                    elif len(password) < 6 or len(password) > 100:
                        return jsonify({'error': 'Длина пароля должна быть от 6 до 100 символов'}), 400
                    
                    # Проверка существования пользователя
                    existing_users = [u[1] for u in self.db_manager.get_all_users()]
                    if username in existing_users:
                        return jsonify({'error': 'Имя пользователя уже существует'}), 400
                    
                    success, message = self.db_manager.add_user(username, password)
                    if success:
                        return jsonify({'message': message}), 201
                    else:
                        return jsonify({'error': message}), 400
                    
                except Exception as e:
                    log_error(f"Ошибка при добавлении пользователя: {e}")
                    return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/users/<username>', methods=['PUT', 'DELETE'])
        @self.require_login
        def api_user_detail(username):
            """API управления деталями пользователя"""
            if request.method == 'PUT':
                # Обновление информации о пользователе (пароль или имя пользователя)
                try:
                    data = request.get_json()
                    if not data:
                        return jsonify({'error': 'Ошибка формата данных запроса'}), 400
                    
                    new_password = data.get('password', '').strip()
                    new_username = data.get('username', '').strip()
                    
                    # Проверка, является ли учетная запись администратором
                    if username == config.DEFAULT_ADMIN['username']:
                        # Администратор может изменить только пароль, имя пользователя изменять нельзя
                        if new_username:
                            return jsonify({'error': 'Имя пользователя администратора нельзя изменить'}), 400
                        
                        if not new_password:
                            return jsonify({'error': 'Новый пароль не может быть пустым'}), 400
                        
                        # Проверка символов пароля
                        password_valid, password_error = self._validate_alphanumeric(new_password, "Новый пароль")
                        if not password_valid:
                            return jsonify({'error': password_error}), 400
                        
                        elif len(new_password) < 6 or len(new_password) > 100:
                            return jsonify({'error': 'Длина нового пароля должна быть от 6 до 100 символов'}), 400
                        
                        # Обновление пароля администратора
                        success = self.db_manager.update_admin_password(username, new_password)
                        if success:
                            return jsonify({'message': f'Пароль администратора {username} успешно обновлен'})
                        else:
                            return jsonify({'error': 'Ошибка обновления пароля администратора'}), 500
                    else:
                        # Обычный пользователь может изменить пароль и имя пользователя
                        if new_username:
                            # Изменение имени пользователя
                            # Проверка символов имени пользователя
                            username_valid, username_error = self._validate_alphanumeric(new_username, "Имя пользователя")
                            if not username_valid:
                                return jsonify({'error': username_error}), 400
                            
                            if len(new_username) < 2 or len(new_username) > 50:
                                return jsonify({'error': 'Длина имени пользователя должна быть от 2 до 50 символов'}), 400
                            
                            # Проверка существования нового имени пользователя
                            existing_users = [u[1] for u in self.db_manager.get_all_users()]
                            if new_username in existing_users and new_username != username:
                                return jsonify({'error': 'Имя пользователя уже существует'}), 400
                            
                            # Принудительное отключение пользователя
                            forwarder.force_disconnect_user(username)
                            
                            # Получение ID пользователя и текущего пароля
                            users = self.db_manager.get_all_users()
                            user_id = None
                            current_password = None
                            for user in users:
                                if user[1] == username:
                                    user_id = user[0]
                                    current_password = user[2]  # Получение текущего хэша пароля
                                    break
                            
                            if user_id is None:
                                return jsonify({'error': 'Пользователь не существует'}), 400
                            
                            # Обновление имени пользователя (сохранение оригинального пароля)
                            success, message = self.db_manager.update_user(user_id, new_username, current_password)
                            if success:
                                return jsonify({'message': f'Имя пользователя обновлено с {username} на {new_username}'})
                            else:
                                return jsonify({'error': message}), 400
                        
                        elif new_password:
                            # Изменение пароля
                            if len(new_password) < 6 or len(new_password) > 100:
                                return jsonify({'error': 'Длина нового пароля должна быть от 6 до 100 символов'}), 400
                            
                            # Принудительное отключение пользователя
                            forwarder.force_disconnect_user(username)
                            success, message = self.db_manager.update_user_password(username, new_password)
                            if success:
                                return jsonify({'message': f'Пароль пользователя {username} успешно обновлен'})
                            else:
                                return jsonify({'error': message}), 400
                        else:
                            return jsonify({'error': 'Предоставьте пароль или имя пользователя для обновления'}), 400
                    
                except Exception as e:
                    log_error(f"Ошибка при обновлении пользователя: {e}")
                    return jsonify({'error': str(e)}), 500
            
            elif request.method == 'DELETE':
                # Удаление пользователя
                try:
                    # Принудительное отключение пользователя
                    forwarder.force_disconnect_user(username)
                    success, result = self.db_manager.delete_user(username)
                    if success:
                        return jsonify({'message': f'Пользователь {result} успешно удален'})
                    else:
                        return jsonify({'error': result}), 400
                    
                except Exception as e:
                    log_error(f"Ошибка при удалении пользователя: {e}")
                    return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/mounts', methods=['GET', 'POST'])
        @self.require_login
        def api_mounts():
            """API управления точками монтирования"""
            if request.method == 'GET':
                # Получение списка точек монтирования
                try:
                    mounts = self.db_manager.get_all_mounts()
                    online_mounts = connection.get_connection_manager().get_online_mounts()
                    
                    # Преобразование tuple в формат словаря и добавление статуса работы и информации о подключениях
                    mount_list = []
                    for mount in mounts:
                        mount_name = mount[1]
                        is_online = mount_name in online_mounts
                        # Получение фактической скорости данных
                        data_rate_str = '0 B/s'
                        if is_online:
                            mount_info = connection.get_connection_manager().get_mount_info(mount_name)
                            if mount_info and 'data_rate' in mount_info:
                                data_rate_bps = mount_info['data_rate']
                                if data_rate_bps >= 1024:
                                    data_rate_str = f'{data_rate_bps/1024:.2f} KB/s'
                                else:
                                    data_rate_str = f'{data_rate_bps:.2f} B/s'
                        
                        mount_dict = {
                            'id': mount[0],
                            'mount': mount_name,
                            'password': mount[2],
                            'username': mount[4] if len(mount) > 4 else None,  # Имя пользователя
                            'lat': mount[5] if len(mount) > 5 and mount[5] is not None else 0,
                            'lon': mount[6] if len(mount) > 6 and mount[6] is not None else 0,
                            'active': is_online,
                            'connections': connection.get_connection_manager().get_mount_connection_count(mount_name) if is_online else 0,
                            'data_rate': data_rate_str
                        }
                        mount_list.append(mount_dict)
                    
                    return jsonify(mount_list)
                except Exception as e:
                    log_error(f"Ошибка при получении списка точек монтирования: {e}")
                    return jsonify({'error': str(e)}), 500
            
            elif request.method == 'POST':
                # Добавление точки монтирования
                try:
                    data = request.get_json()
                    if not data:
                        return jsonify({'error': 'Ошибка формата данных запроса'}), 400
                    
                    mount = data.get('mount', '').strip()
                    password = data.get('password', '').strip()
                    user_id = data.get('user_id')  # Необязательный параметр ID пользователя
                    
                    # Валидация формы
                    if not mount or not password:
                        return jsonify({'error': 'Имя точки монтирования и пароль не могут быть пустыми'}), 400
                    
                    # Проверка символов имени точки монтирования
                    mount_valid, mount_error = self._validate_alphanumeric(mount, "Имя точки монтирования")
                    if not mount_valid:
                        return jsonify({'error': mount_error}), 400
                    
                    # Проверка символов пароля
                    password_valid, password_error = self._validate_alphanumeric(password, "Пароль")
                    if not password_valid:
                        return jsonify({'error': password_error}), 400
                    
                    elif len(mount) < 2 or len(mount) > 50:
                        return jsonify({'error': 'Длина имени точки монтирования должна быть от 2 до 50 символов'}), 400
                    elif len(password) < 6 or len(password) > 100:
                        return jsonify({'error': 'Длина пароля должна быть от 6 до 100 символов'}), 400
                    
                    # Если указан user_id, проверка существования пользователя
                    if user_id is not None:
                        try:
                            user_id = int(user_id)
                            users = self.db_manager.get_all_users()
                            user_ids = [u[0] for u in users]  # u[0] - это ID пользователя
                            if user_id not in user_ids:
                                return jsonify({'error': 'Указанный пользователь не существует'}), 400
                        except (ValueError, TypeError):
                            return jsonify({'error': 'Ошибка формата ID пользователя'}), 400
                    
                    # Проверка существования точки монтирования
                    existing_mounts = [m[1] for m in self.db_manager.get_all_mounts()]
                    if mount in existing_mounts:
                        return jsonify({'error': 'Точка монтирования уже существует'}), 400
                    
                    success, message = self.db_manager.add_mount(mount, password, user_id)
                    if success:
                        return jsonify({'message': message}), 201
                    else:
                        return jsonify({'error': message}), 400
                    
                except Exception as e:
                    log_error(f"Ошибка при добавлении точки монтирования: {e}")
                    return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/mounts/<mount_name>', methods=['PUT', 'DELETE'])
        @self.require_login
        def api_mount_detail(mount_name):
            """API управления деталями точки монтирования"""
            if request.method == 'PUT':
                # Обновление точки монтирования
                try:
                    data = request.get_json()
                    if not data:
                        return jsonify({'error': 'Ошибка формата данных запроса'}), 400
                    
                    new_password = data.get('password', '').strip()
                    new_mount_name = data.get('mount_name', '').strip()
                    new_user_id = data.get('user_id')
                    username = data.get('username')
                    
                    # Валидация нового имени точки монтирования
                    if new_mount_name:
                        # Проверка символов имени точки монтирования
                        mount_valid, mount_error = self._validate_alphanumeric(new_mount_name, "Имя точки монтирования")
                        if not mount_valid:
                            return jsonify({'error': mount_error}), 400
                        
                        if len(new_mount_name) < 2 or len(new_mount_name) > 50:
                            return jsonify({'error': 'Длина имени точки монтирования должна быть от 2 до 50 символов'}), 400
                        
                        # Проверка существования нового имени точки монтирования
                        existing_mounts = [m[1] for m in self.db_manager.get_all_mounts()]
                        if new_mount_name in existing_mounts and new_mount_name != mount_name:
                            return jsonify({'error': 'Имя точки монтирования уже существует'}), 400
                    
                    # Обработка привязки пользователя (поддержка имени пользователя и ID пользователя)
                    if username is not None:
                        if username == "" or (isinstance(username, str) and username.lower() == "null"):
                            new_user_id = None  # Пустая строка или "null" означает отвязку
                        else:
                            # Проверка символов имени пользователя
                            username_valid, username_error = self._validate_alphanumeric(username, "Имя пользователя")
                            if not username_valid:
                                return jsonify({'error': username_error}), 400
                            
                            # Поиск ID пользователя по имени пользователя
                            users = self.db_manager.get_all_users()
                            user_found = False
                            for user in users:
                                if user[1] == username:  # user[1] - это имя пользователя
                                    new_user_id = user[0]  # user[0] - это ID пользователя
                                    user_found = True
                                    break
                            if not user_found:
                                return jsonify({'error': f'Пользователь "{username}" не существует'}), 400
                    elif new_user_id is not None:
                        # Совместимость с существующим способом использования ID пользователя
                        if new_user_id == "" or (isinstance(new_user_id, str) and new_user_id.lower() == "null"):
                            new_user_id = None  # Пустая строка или "null" преобразуется в None
                        elif new_user_id is not None:
                            try:
                                new_user_id = int(new_user_id)
                                # Проверка существования пользователя
                                users = self.db_manager.get_all_users()
                                user_exists = any(user[0] == new_user_id for user in users)
                                if not user_exists:
                                    return jsonify({'error': 'Указанный пользователь не существует'}), 400
                            except (ValueError, TypeError):
                                return jsonify({'error': 'Ошибка формата ID пользователя'}), 400
                    
                    if new_password:
                        # Проверка символов пароля
                        password_valid, password_error = self._validate_alphanumeric(new_password, "Пароль")
                        if not password_valid:
                            return jsonify({'error': password_error}), 400
                        
                        if len(new_password) < 6 or len(new_password) > 100:
                            return jsonify({'error': 'Длина нового пароля должна быть от 6 до 100 символов'}), 400
                    
                    # Принудительное отключение точки монтирования
                    forwarder.force_disconnect_mount(mount_name)
                    
                    # Получение ID точки монтирования
                    mounts = self.db_manager.get_all_mounts()
                    mount_id = None
                    for mount in mounts:
                        if mount[1] == mount_name:  # mount[1] - это имя точки монтирования
                            mount_id = mount[0]  # mount[0] - это ID
                            break
                    
                    if mount_id is None:
                        return jsonify({'error': 'Точка монтирования не существует'}), 400
                    
                    # Использование функции update_mount для обновления информации о точке монтирования
                    success, result = self.db_manager.update_mount(
                        mount_id, 
                        new_mount_name if new_mount_name else None,
                        new_password if new_password else None,
                        new_user_id
                    )
                    if success:
                        # Формирование сообщения ответа
                        messages = []
                        if new_mount_name:
                            messages.append(f'Имя точки монтирования обновлено с {mount_name} на {new_mount_name}')
                        if new_password:
                            messages.append('Пароль точки монтирования обновлен')
                        if 'username' in data or new_user_id is not None:
                            if new_user_id is None:
                                messages.append('Привязка точки монтирования к пользователю удалена')
                            else:
                                if username and username != "":
                                    messages.append(f'Пользователь точки монтирования обновлен на {username}')
                                else:
                                    messages.append(f'Пользователь точки монтирования обновлен на ID {new_user_id}')
                        
                        if not messages:
                            messages.append('Информация о точке монтирования успешно обновлена')
                        
                        return jsonify({'message': '; '.join(messages)})
                    else:
                        return jsonify({'error': result}), 400
                    
                except Exception as e:
                    log_error(f"Ошибка при обновлении точки монтирования: {e}")
                    return jsonify({'error': str(e)}), 500
            
            elif request.method == 'DELETE':
                # Удаление точки монтирования
                try:
                    # Получение ID точки монтирования
                    mounts = self.db_manager.get_all_mounts()
                    mount_id = None
                    for mount in mounts:
                        if mount[1] == mount_name:  # mount[1] - это имя точки монтирования
                            mount_id = mount[0]  # mount[0] - это ID
                            break
                    
                    if mount_id is None:
                        return jsonify({'error': 'Точка монтирования не существует'}), 400
                    
                    # Принудительное отключение точки монтирования
                    forwarder.force_disconnect_mount(mount_name)
                    success, result = self.db_manager.delete_mount(mount_name)
                    if success:
                        # Очистка данных подключений точки монтирования
                        connection.get_connection_manager().remove_mount_connection(mount_name)
                        return jsonify({'message': f'Точка монтирования {result} успешно удалена'})
                    else:
                        return jsonify({'error': result}), 400
                    
                except Exception as e:
                    log_error(f"Ошибка при удалении точки монтирования: {e}")
                    return jsonify({'error': str(e)}), 500

        

        

        
        @self.app.route('/api/mount/<mount_name>/online')
        @self.require_login
        def api_mount_online_status(mount_name):
            """Проверка статуса точки монтирования (онлайн/офлайн)"""
            try:
                is_online = connection.is_mount_online(mount_name)
                mount_info = None
                if is_online:
                    mount_info = connection.get_connection_manager().get_mount_info(mount_name)
                
                return jsonify({
                    'mount_name': mount_name,
                    'online': is_online,
                    'mount_info': mount_info
                })
            except Exception as e:
                log_error(f"Ошибка при проверке статуса точки монтирования: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/system/stats')
        def api_system_stats():
            """Получение системной статистики"""
            try:
                # Получение экземпляра сервера
                server = get_server_instance()
                if server and hasattr(server, 'get_system_stats'):
                    stats = server.get_system_stats()
                
                    return jsonify(stats)
                else:
                    log_error("Ошибка API: не удалось получить экземпляр сервера или метод get_system_stats")
                    return jsonify({'error': 'Не удалось получить системную статистику'}), 500
            except Exception as e:
                log_error(f"Исключение API: ошибка при получении системной статистики: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/str-table', methods=['GET'])
        def api_str_table():
            """Получение данных таблицы STR в реальном времени"""
            try:
                # Получение данных STR всех онлайн точек монтирования
                cm = connection.get_connection_manager()
                str_data = cm.get_all_str_data()
                
                # Генерация полного списка точек монтирования (включая таблицу STR)
                mount_list = cm.generate_mount_list()
                
                return jsonify({
                    'success': True,
                    'str_data': str_data,
                    'mount_list': mount_list,
                    'timestamp': time.time()
                })
            except Exception as e:
                log_error(f"Ошибка при получении таблицы STR: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/mounts/online', methods=['GET'])
        def api_online_mounts_detailed():
            """Получение подробной информации об онлайн точках монтирования"""
            try:
                cm = connection.get_connection_manager()
                online_mounts = cm.get_online_mounts()
                
                # Добавление подробной информации для каждой точки монтирования
                detailed_mounts = {}
                for mount_name, mount_info in online_mounts.items():
                    detailed_mounts[mount_name] = {
                        'basic_info': mount_info,
                        'str_data': cm.get_mount_str_data(mount_name),
                        'statistics': cm.get_mount_statistics(mount_name),
                        'connection_count': cm.get_mount_connection_count(mount_name)
                    }
                
                return jsonify({
                    'success': True,
                    'online_mounts': detailed_mounts,
                    'total_count': len(detailed_mounts),
                    'timestamp': time.time()
                })
            except Exception as e:
                log_error(f"Ошибка при получении исторических данных точки монтирования {mount_name}: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/mount/<mount_name>/rtcm-parse/history', methods=['GET'])
        @self.require_login
        def api_get_rtcm_history(mount_name):
            """Получение исторических данных разбора для указанной точки монтирования"""
            try:
                # Получение результатов разбора
                parsed_data = rtcm_manager.get_parsed_mount_data(mount_name)
                if parsed_data:
                    return jsonify({
                        'success': True,
                        'data': parsed_data
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'No data available for this mount point'
                    }), 404
            except Exception as e:
                log_error(f"Ошибка при получении исторических данных точки монтирования {mount_name}: {e}")
                return jsonify({'error': str(e)}), 500

    
    def _ensure_forwarder_started(self):
        """Обеспечение запуска forwarder (уже запущен в main.py, метод оставлен для совместимости)"""
        # forwarder уже запущен в main.py, здесь повторный запуск не требуется
        pass
    
    def _register_socketio_events(self):
        """Регистрация событий SocketIO"""
        
        @self.socketio.on('connect')
        def handle_connect():
            """Подключение клиента"""
            from flask import session
            client_id = session.get('sid', 'unknown')
            log_web_request('websocket', 'connect', client_id, 'WebSocket клиент подключен')
            # Добавление клиента в комнату для отправки данных
            join_room('data_push')
            if config.LOG_FREQUENT_STATUS:
                log_info(f"Клиент {client_id} присоединился к комнате data_push")
            emit('status', {'message': 'Подключение успешно'})
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Отключение клиента"""
            from flask import session
            client_id = session.get('sid', 'unknown')
            log_web_request('websocket', 'disconnect', client_id, 'WebSocket клиент отключен')
            
            # При отключении WebSocket автоматически очистить поток веб-разбора
            try:
                # Получение текущей активной точки монтирования для веб-разбора
                current_web_mount = rtcm_manager.get_current_web_mount()
                if current_web_mount:
                    log_info(f"Отключение WebSocket, автоматическая очистка потока веб-разбора [точка монтирования: {current_web_mount}]")
                    rtcm_manager.stop_realtime_parsing()
                    log_system_event(f"Отключение WebSocket, автоматически очищен поток веб-разбора: {current_web_mount}")
                else:
                    log_debug("Отключение WebSocket, но нет активных потоков веб-разбора для очистки")
            except Exception as e:
                log_error(f"Ошибка при очистке потока веб-разбора при отключении WebSocket: {e}")
        
        @self.socketio.on('request_mount_data')
        def handle_request_mount_data(data):
            """Запрос данных точки монтирования"""
            mount = data.get('mount')
            if mount:
                parsed_data = rtcm_manager.get_parsed_mount_data(mount)
                statistics = rtcm_manager.get_mount_statistics(mount)
                emit('mount_data', {
                    'mount': mount,
                    'data': parsed_data,
                    'statistics': statistics
                })
        
        @self.socketio.on('request_recent_data')
        def handle_request_recent_data(data):
            """Запрос последних разобранных данных точки монтирования от фронтенда"""
            mount_name = data.get('mount_name')
            if mount_name:
                recent_data = rtcm_manager.get_parsed_mount_data(mount_name)
                emit('recent_data_response', {
                    'mount_name': mount_name,
                    'data': recent_data
                })
        
        @self.socketio.on('request_system_stats')
        def handle_request_system_stats():
            """Запрос системной статистики"""
            try:
                server = get_server_instance()
                if server and hasattr(server, 'get_system_stats'):
                    stats = server.get_system_stats()
                    if stats:
                        emit('system_stats_update', {
                            'stats': stats,
                            'timestamp': time.time()
                        })
                    else:
                        emit('error', {'message': 'Не удалось получить системную статистику'})
                else:
                    emit('error', {'message': 'Экземпляр сервера недоступен'})
            except Exception as e:
                log_error(f"Ошибка при обработке запроса системной статистики: {e}")
                emit('error', {'message': str(e)})
    
    def require_login(self, f):
        """Декоратор для проверки авторизации"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('admin_logged_in'):
                # Проверка, является ли запрос API-запросом
                if request.path.startswith('/api/'):
                    return jsonify({'error': 'Не авторизован или сессия истекла'}), 401
                else:
                    return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    
    def start_rtcm_parsing(self):
        """Запуск процесса разбора RTCM, постоянный разбор данных и отправка на фронтенд"""
        # Теперь разбор RTCM интегрирован в connection_manager, отдельный запуск не требуется
        
        # Запуск отправки данных в реальном времени
        if not self.push_running:
            self.push_running = True
            self.push_thread = Thread(target=self._push_data_loop, daemon=True)
            self.push_thread.start()
            log_system_event('Отправка веб-данных в реальном времени запущена')
    
    def stop_rtcm_parsing(self):
        """Остановка разбора RTCM"""
        # Теперь разбор RTCM интегрирован в connection_manager, отдельная остановка не требуется
        
        # Остановка отправки данных в реальном времени
        if self.push_running:
            self.push_running = False
            if self.push_thread:
                self.push_thread.join(timeout=5)
            log_system_event('Отправка веб-данных в реальном времени остановлена')
    
    def _push_data_loop(self):
        """Цикл отправки данных в реальном времени"""
        log_info("Цикл отправки данных запущен")
        while self.push_running:
            try:
                # Отправка системной статистики
                server = get_server_instance()
                if server and hasattr(server, 'get_system_stats'):
                    stats = server.get_system_stats()
                    if stats:
                        self.socketio.emit('system_stats_update', {
                            'stats': stats,
                            'timestamp': time.time()
                        }, to='data_push')
                        # Удален вывод отладочного лога
                pass
                
                # Отправка списка онлайн пользователей
                online_users = connection.get_connection_manager().get_online_users()
                self.socketio.emit('online_users_update', {
                    'users': online_users,
                    'timestamp': time.time()
                }, to='data_push')
                # Удален вывод отладочного лога
                pass
                
                # Отправка списка онлайн точек монтирования
                online_mounts = connection.get_connection_manager().get_online_mounts()
                self.socketio.emit('online_mounts_update', {
                    'mounts': online_mounts,
                    'timestamp': time.time()
                }, to='data_push')
                # Удален вывод отладочного лога
                pass
                
                # Отправка данных таблицы STR
                str_data = connection.get_connection_manager().get_all_str_data()
                self.socketio.emit('str_data_update', {
                    'str_data': str_data,
                    'timestamp': time.time()
                }, to='data_push')
                # Удален вывод отладочного лога
                pass
                
                time.sleep(config.REALTIME_PUSH_INTERVAL)
            except Exception as e:
                log_error(f"Исключение при отправке данных: {e}", exc_info=True)
                time.sleep(1)
    
    def push_log_message(self, message, log_type='info'):
        """Отправка сообщения лога на фронтенд"""
        try:
            self.socketio.emit('log_message', {
                'message': message,
                'type': log_type,
                'timestamp': time.time()
            }, to='data_push')
        except Exception as e:
            log_error(f"Ошибка при отправке сообщения лога: {e}")
    
    def _format_uptime(self, uptime_seconds):
        """Форматирование времени работы"""
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        
        if days > 0:
            return f"{days} дн. {hours} ч. {minutes} мин."
        elif hours > 0:
            return f"{hours} ч. {minutes} мин."
        else:
            return f"{minutes} мин. {seconds} сек."
    

    
    def run(self, host=None, port=None, debug=None):
        """Запуск веб-сервера"""
        host = host or config.HOST
        port = port or config.WEB_PORT
        debug = debug if debug is not None else config.DEBUG
        self.socketio.run(self.app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
    

# Вспомогательная функция
def create_web_manager(db_manager, data_forwarder, start_time):
    """Создание экземпляра веб-менеджера"""
    return WebManager(db_manager, data_forwarder, start_time)