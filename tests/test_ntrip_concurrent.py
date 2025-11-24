#!/usr/bin/env python3
"""
Скрипт тестирования параллельных подключений NTRIP
Функция: использование 500 пользователей для параллельного подключения к NTRIP-серверу, тестирование стабильности системы
"""

import socket
import threading
import time
import json
import random
import base64
import hashlib
import sys
import psutil
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Конфигурация NTRIP-сервера
NTRIP_SERVER = "192.168.1.4"
NTRIP_PORT = 2101
MOUNT_POINTS = ["RTKGL", "RTKHL"]
TEST_DURATION = 99999  # Длительность теста (секунды), поддержание длинных подключений
MAX_CONCURRENT_CONNECTIONS = 1500  # Максимальное количество параллельных подключений
TARGET_CONNECTIONS = [1000, 1200, 1500]  # Список целевых подключений
CONNECTION_STEP = 100  # Количество подключений, добавляемых каждый раз

# Статистическая информация
stats = {
    "total_connections": 0,
    "successful_connections": 0,
    "failed_connections": 0,
    "data_received": 0,
    "total_bytes": 0,
    "ntrip_bytes_sent": 0,      # Количество байт, отправленных на уровне приложения NTRIP
    "ntrip_bytes_received": 0,  # Количество байт, полученных на уровне приложения NTRIP
    "connection_errors": [],
    "start_time": None,
    "end_time": None,
    "performance_data": [],
    "server_stats": [],
    "network_stats": []
}
stats_lock = threading.Lock()

def load_test_users():
    """Загрузка списка тестовых пользователей"""
    try:
        with open("test_users.json", "r", encoding="utf-8") as f:
            users = json.load(f)
        print(f"Успешно загружено {len(users)} тестовых пользователей")
        return users
    except FileNotFoundError:
        print("Ошибка: файл test_users.json не найден, сначала запустите test_add_users.py")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка загрузки файла пользователей: {e}")
        sys.exit(1)

def get_system_performance():
    """Получение данных производительности системы"""
    try:
        # Использование CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Использование памяти
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_mb = memory.used / 1024 / 1024
        memory_total_mb = memory.total / 1024 / 1024
        
        # Статистика сетевого ввода-вывода
        net_io = psutil.net_io_counters()
        
        return {
            "timestamp": time.time(),
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "memory_used_mb": memory_used_mb,
            "memory_total_mb": memory_total_mb,
            "network_bytes_sent": net_io.bytes_sent,
            "network_bytes_recv": net_io.bytes_recv,
            "network_packets_sent": net_io.packets_sent,
            "network_packets_recv": net_io.packets_recv
        }
    except Exception as e:
        print(f"Ошибка получения данных производительности системы: {e}")
        return None

def get_server_stats():
    """Получение статистики NTRIP-сервера"""
    try:
        # Попытка получить статистику через API сервера
        response = requests.get(f"http://{NTRIP_SERVER}:5757/api/stats", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Ошибка получения статистики сервера: {e}")
    return None

def calculate_bandwidth(start_stats, end_stats, duration):
    """Вычисление использования сетевой пропускной способности"""
    if not start_stats or not end_stats or duration <= 0:
        return None
    
    bytes_sent_diff = end_stats["network_bytes_sent"] - start_stats["network_bytes_sent"]
    bytes_recv_diff = end_stats["network_bytes_recv"] - start_stats["network_bytes_recv"]
    
    upload_mbps = (bytes_sent_diff * 8) / (duration * 1024 * 1024)  # Mbps
    download_mbps = (bytes_recv_diff * 8) / (duration * 1024 * 1024)  # Mbps
    
    return {
        "upload_mbps": upload_mbps,
        "download_mbps": download_mbps,
        "total_mbps": upload_mbps + download_mbps,
        "bytes_sent": bytes_sent_diff,
        "bytes_recv": bytes_recv_diff
    }

def create_ntrip_request(mount_point, username, password, protocol="basic"):
    """Создание NTRIP-запроса"""
    if protocol == "basic":
        # Базовая аутентификация
        auth_string = f"{username}:{password}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        request = (
            f"GET /{mount_point} HTTP/1.1\r\n"
            f"Host: {NTRIP_SERVER}:{NTRIP_PORT}\r\n"
            f"User-Agent: NTRIP-Test-Client/1.0\r\n"
            f"Authorization: Basic {auth_b64}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
    elif protocol == "digest":
        # Digest-аутентификация (упрощенная версия, в реальном приложении сначала нужно получить challenge)
        request = (
            f"GET /{mount_point} HTTP/1.1\r\n"
            f"Host: {NTRIP_SERVER}:{NTRIP_PORT}\r\n"
            f"User-Agent: NTRIP-Test-Client/1.0\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
    else:
        # Формат NTRIP 1.0
        request = (
            f"GET /{mount_point} HTTP/1.0\r\n"
            f"User-Agent: NTRIP-Test-Client/1.0\r\n"
            f"Authorization: Basic {base64.b64encode(f'{username}:{password}'.encode()).decode()}\r\n"
            f"\r\n"
        )
    
    return request

def ntrip_client_test(user_info, test_duration):
    """Тест одного NTRIP-клиента"""
    username = user_info["username"]
    password = user_info["password"]
    mount_point = random.choice(MOUNT_POINTS)
    protocol = random.choice(["basic", "ntrip1.0"])  # Случайный выбор протокола
    
    client_stats = {
        "username": username,
        "mount_point": mount_point,
        "protocol": protocol,
        "connected": False,
        "bytes_received": 0,
        "connection_time": 0,
        "error_message": None
    }
    
    sock = None
    start_time = time.time()
    
    try:
        # Создание socket-подключения
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)  # Таймаут 30 секунд, дать серверу больше времени на обработку
        
        # Подключение к NTRIP-серверу
        sock.connect((NTRIP_SERVER, NTRIP_PORT))
        
        # Отправка NTRIP-запроса
        request = create_ntrip_request(mount_point, username, password, protocol)
        request_bytes = request.encode('utf-8')
        sock.send(request_bytes)
        
        # Подсчет отправленных байт NTRIP
        with stats_lock:
            stats["ntrip_bytes_sent"] += len(request_bytes)
        
        # Получение ответа
        response = sock.recv(1024).decode('utf-8', errors='ignore')
        
        if "200 OK" in response:
            client_stats["connected"] = True
            client_stats["connection_time"] = time.time() - start_time
            
            # Непрерывный прием данных
            end_time = start_time + test_duration
            sock.settimeout(1)  # Установка более короткого таймаута для приема
            
            while time.time() < end_time:
                try:
                    data = sock.recv(4096)
                    if data:
                        client_stats["bytes_received"] += len(data)
                        # Подсчет полученных байт NTRIP
                        with stats_lock:
                            stats["ntrip_bytes_received"] += len(data)
                    else:
                        break
                except socket.timeout:
                    continue
                except Exception:
                    break
        else:
            client_stats["error_message"] = f"Ошибка аутентификации: {response[:100]}"
    
    except socket.timeout:
        client_stats["error_message"] = "Таймаут подключения"
    except ConnectionRefusedError:
        client_stats["error_message"] = "Подключение отклонено"
    except Exception as e:
        client_stats["error_message"] = str(e)
    
    finally:
        if sock:
            try:
                sock.close()
            except:
                pass
    
    # Обновление глобальной статистики
    with stats_lock:
        stats["total_connections"] += 1
        if client_stats["connected"]:
            stats["successful_connections"] += 1
            stats["total_bytes"] += client_stats["bytes_received"]
            if client_stats["bytes_received"] > 0:
                stats["data_received"] += 1
        else:
            stats["failed_connections"] += 1
            if client_stats["error_message"]:
                stats["connection_errors"].append({
                    "username": username,
                    "mount_point": mount_point,
                    "error": client_stats["error_message"]
                })
    
    return client_stats

def print_progress():
    """Вывод прогресса тестирования и мониторинг производительности"""
    last_perf_data = None
    
    while stats["start_time"] and not stats["end_time"]:
        time.sleep(5)  # Печать каждые 5 секунд
        
        # Получение данных производительности
        current_perf = get_system_performance()
        server_stats = get_server_stats()
        
        with stats_lock:
            elapsed = time.time() - stats["start_time"]
            
            # Сохранение данных производительности
            if current_perf:
                stats["performance_data"].append(current_perf)
            if server_stats:
                stats["server_stats"].append(server_stats)
            
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Прогресс тестирования и мониторинг производительности:")
            print(f"  Время работы: {elapsed:.1f}s")
            print(f"  Всего подключений: {stats['total_connections']}")
            print(f"  Успешных подключений: {stats['successful_connections']}")
            print(f"  Неудачных подключений: {stats['failed_connections']}")
            print(f"  Подключений с получением данных: {stats['data_received']}")
            print(f"  Всего получено байт: {stats['total_bytes']:,} ({stats['total_bytes']/1024/1024:.2f} MB)")
            print(f"  NTRIP отправлено: {stats['ntrip_bytes_sent']:,} байт ({stats['ntrip_bytes_sent']/1024:.2f} KB)")
            print(f"  NTRIP получено: {stats['ntrip_bytes_received']:,} байт ({stats['ntrip_bytes_received']/1024/1024:.2f} MB)")
            
            if stats['successful_connections'] > 0:
                success_rate = (stats['successful_connections'] / stats['total_connections']) * 100
                print(f"  Процент успешных подключений: {success_rate:.1f}%")
            
            # Отображение производительности системы
            if current_perf:
                print(f"\n  Производительность системы:")
                print(f"    Использование CPU: {current_perf['cpu_percent']:.1f}%")
                print(f"    Использование памяти: {current_perf['memory_percent']:.1f}% ({current_perf['memory_used_mb']:.0f}/{current_perf['memory_total_mb']:.0f} MB)")
                
                # Вычисление сетевой пропускной способности
                if last_perf_data:
                    bandwidth = calculate_bandwidth(last_perf_data, current_perf, 5)
                    if bandwidth:
                        print(f"    Сетевая пропускная способность: ↑{bandwidth['upload_mbps']:.2f} Mbps ↓{bandwidth['download_mbps']:.2f} Mbps (всего: {bandwidth['total_mbps']:.2f} Mbps)")
                        print(f"    Передача данных: ↑{bandwidth['bytes_sent']/1024/1024:.2f} MB ↓{bandwidth['bytes_recv']/1024/1024:.2f} MB")
                
                last_perf_data = current_perf
            
            # Отображение статистики сервера
            if server_stats:
                print(f"\n  Состояние сервера:")
                if 'active_connections' in server_stats:
                    print(f"    Активные подключения: {server_stats['active_connections']}")
                if 'total_connections' in server_stats:
                    print(f"    Всего подключений: {server_stats['total_connections']}")
                if 'rejected_connections' in server_stats:
                    print(f"    Отклоненные подключения: {server_stats['rejected_connections']}")

def run_connection_test(users, target_connections, test_name):
    """Запуск теста указанного количества подключений"""
    print(f"\n{'='*60}")
    print(f"Начало {test_name} - целевое количество подключений: {target_connections}")
    print(f"{'='*60}")
    
    # Сброс статистических данных
    with stats_lock:
        stats["total_connections"] = 0
        stats["successful_connections"] = 0
        stats["failed_connections"] = 0
        stats["data_received"] = 0
        stats["total_bytes"] = 0
        stats["ntrip_bytes_sent"] = 0
        stats["ntrip_bytes_received"] = 0
        stats["connection_errors"] = []
        stats["performance_data"] = []
        stats["server_stats"] = []
        stats["start_time"] = time.time()
        stats["end_time"] = None
    
    # Получение начальных данных производительности
    initial_perf = get_system_performance()
    
    # Запуск потока отображения прогресса
    progress_thread = threading.Thread(target=print_progress, daemon=True)
    progress_thread.start()
    
    # Выбор подмножества пользователей, обеспечение соблюдения лимита подключений на одного пользователя
    MAX_CONNECTIONS_PER_USER = 50  # Соответствие конфигурационному файлу
    test_users = []
    user_connection_count = {}
    
    # Циклическое распределение пользователей, обеспечение соблюдения лимита подключений на одного пользователя
    user_index = 0
    for i in range(target_connections):
        while True:
            user = users[user_index % len(users)]
            username = user['username']
            
            # Проверка количества подключений этого пользователя
            if user_connection_count.get(username, 0) < MAX_CONNECTIONS_PER_USER:
                test_users.append(user)
                user_connection_count[username] = user_connection_count.get(username, 0) + 1
                break
            
            user_index += 1
            # Если все пользователи достигли лимита подключений, прекратить распределение
            if user_index >= len(users) * MAX_CONNECTIONS_PER_USER:
                print(f"Предупреждение: невозможно выделить {target_connections} подключений, максимально можно выделить {len(test_users)} подключений")
                break
        
        if len(test_users) >= target_connections or user_index >= len(users) * MAX_CONNECTIONS_PER_USER:
            break
        
        user_index += 1
    
    print(f"Используется {len(test_users)} пользователей для тестирования...")
    
    # Использование пула потоков для параллельного тестирования
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CONNECTIONS) as executor:
        futures = []
        for i, user in enumerate(test_users):
            # Тест длительного подключения
            future = executor.submit(ntrip_client_test, user, TEST_DURATION)
            futures.append(future)
            
            # Управление скоростью установления подключений
            time.sleep(0.02)  # Установление подключения каждые 20 мс
            
            if (i + 1) % 100 == 0:
                print(f"Запущено {i + 1}/{len(test_users)} подключений...")
        
        print(f"\nВсе {len(test_users)} подключений запущены, ожидание стабилизации работы...")
        
        # Ожидание стабилизации подключений (60 секунд)
        time.sleep(60)
        
        print(f"\nПодключения стабилизированы, начало этапа мониторинга производительности...")
        print("Нажмите Ctrl+C для остановки текущего теста и перехода к следующему этапу")
        
        try:
            # Непрерывный мониторинг до прерывания пользователем
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            print(f"\nПользователь прервал, остановка {test_name}...")
    
    # Запись времени окончания
    with stats_lock:
        stats["end_time"] = time.time()
    
    # Получение финальных данных производительности
    final_perf = get_system_performance()
    
    # Генерация отчета о тестировании
    generate_test_report(test_name, target_connections, initial_perf, final_perf)

def generate_test_report(test_name, target_connections, initial_perf, final_perf):
    """Генерация подробного отчета о тестировании"""
    print(f"\n{'='*60}")
    print(f"Отчет о тестировании {test_name}")
    print(f"{'='*60}")
    
    with stats_lock:
        total_time = stats["end_time"] - stats["start_time"] if stats["end_time"] else 0
        
        print(f"\nОсновная статистика:")
        print(f"  Целевое количество подключений: {target_connections}")
        print(f"  Фактических попыток подключения: {stats['total_connections']}")
        print(f"  Успешных подключений: {stats['successful_connections']}")
        print(f"  Неудачных подключений: {stats['failed_connections']}")
        print(f"  Подключений с получением данных: {stats['data_received']}")
        print(f"  Общее время тестирования: {total_time:.2f} сек")
        
        if stats['total_connections'] > 0:
            success_rate = (stats['successful_connections'] / stats['total_connections']) * 100
            print(f"  Процент успешных подключений: {success_rate:.2f}%")
        
        print(f"\nСтатистика передачи данных:")
        print(f"  Всего получено данных: {stats['total_bytes']:,} байт ({stats['total_bytes']/1024/1024:.2f} MB)")
        print(f"  Статистика на уровне приложения NTRIP:")
        print(f"    Отправлено данных: {stats['ntrip_bytes_sent']:,} байт ({stats['ntrip_bytes_sent']/1024/1024:.2f} MB)")
        print(f"    Получено данных: {stats['ntrip_bytes_received']:,} байт ({stats['ntrip_bytes_received']/1024/1024:.2f} MB)")
        if stats['successful_connections'] > 0 and total_time > 0:
            avg_throughput = (stats['total_bytes'] / total_time) / 1024 / 1024  # MB/s
            ntrip_throughput = (stats['ntrip_bytes_received'] / total_time) / 1024 / 1024  # MB/s
            print(f"  Средняя пропускная способность: {avg_throughput:.2f} MB/s")
            print(f"  Средняя пропускная способность NTRIP: {ntrip_throughput:.2f} MB/s")
            avg_per_conn = stats['total_bytes'] / stats['successful_connections'] / 1024  # KB per connection
            ntrip_avg_per_conn = stats['ntrip_bytes_received'] / stats['successful_connections'] / 1024  # KB per connection
            print(f"  Среднее количество данных на подключение: {avg_per_conn:.2f} KB")
            print(f"  Среднее количество данных NTRIP на подключение: {ntrip_avg_per_conn:.2f} KB")
        
        # Статистика производительности
        if initial_perf and final_perf and len(stats['performance_data']) > 0:
            print(f"\nСтатистика производительности системы:")
            
            # Статистика CPU
            cpu_values = [p['cpu_percent'] for p in stats['performance_data']]
            print(f"  Использование CPU: среднее {sum(cpu_values)/len(cpu_values):.1f}%, максимум {max(cpu_values):.1f}%")
            
            # Статистика памяти
            memory_values = [p['memory_percent'] for p in stats['performance_data']]
            print(f"  Использование памяти: среднее {sum(memory_values)/len(memory_values):.1f}%, максимум {max(memory_values):.1f}%")
            
            # Статистика сетевой пропускной способности
            if total_time > 0:
                bandwidth = calculate_bandwidth(initial_perf, final_perf, total_time)
                if bandwidth:
                    print(f"  Использование сетевой пропускной способности:")
                    print(f"    Загрузка: {bandwidth['upload_mbps']:.2f} Mbps ({bandwidth['bytes_sent']/1024/1024:.2f} MB)")
                    print(f"    Скачивание: {bandwidth['download_mbps']:.2f} Mbps ({bandwidth['bytes_recv']/1024/1024:.2f} MB)")
                    print(f"    Всего: {bandwidth['total_mbps']:.2f} Mbps")
        
        # Статистика ошибок
        if stats['connection_errors']:
            print(f"\nСтатистика ошибок (первые 10):")
            error_counts = {}
            for error in stats['connection_errors'][:20]:
                error_type = error['error'][:100]
                error_counts[error_type] = error_counts.get(error_type, 0) + 1
            
            for error_type, count in list(error_counts.items())[:10]:
                print(f"  {error_type}: {count} раз")
            
            print(f"\nПримеры деталей ошибок (первые 5):")
            for i, error in enumerate(stats['connection_errors'][:5]):
                print(f"  {i+1}. Пользователь: {error['username']}, Точка монтирования: {error['mount_point']}, Ошибка: {error['error']}")
        
        # Сохранение подробного отчета в файл
        report_filename = f"test_report_{test_name}_{target_connections}conn_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_data = {
            "test_name": test_name,
            "target_connections": target_connections,
            "stats": dict(stats),
            "initial_performance": initial_perf,
            "final_performance": final_perf,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            with open(report_filename, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            print(f"\nПодробный отчет сохранен в: {report_filename}")
        except Exception as e:
            print(f"\nОшибка сохранения отчета: {e}")
    
    print(f"\n{test_name} завершен!\n")



def main():
    """Главная функция - запуск многоэтапного параллельного тестирования"""
    print("=" * 80)
    print("Тестирование высокого параллелизма подключений NTRIP - многоэтапное тестирование")
    print("=" * 80)
    
    # Загрузка тестовых пользователей
    users = load_test_users()
    print(f"Загружено {len(users)} тестовых пользователей")
    
    # Конфигурация этапов тестирования
    test_stages = [500, 1000, 1200, 1500, 2000]
    
    for stage_connections in test_stages:
        print(f"\n{'='*60}")
        print(f"Начало параллельного тестирования {stage_connections} подключений")
        print(f"{'='*60}")
        
        try:
            # Запуск теста
            test_name = f"Параллельное тестирование {stage_connections} подключений"
            run_connection_test(users, stage_connections, test_name)
            
            # Интервал между тестами
            if stage_connections != test_stages[-1]:
                print(f"\nОжидание 30 секунд перед следующим этапом тестирования...")
                time.sleep(30)
                
        except KeyboardInterrupt:
            print("\nПользователь прервал тестирование")
            break
        except Exception as e:
            print(f"\nОшибка на этапе тестирования {stage_connections} подключений: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print("\n" + "=" * 80)
    print("Все этапы тестирования завершены")
    print("=" * 80)

if __name__ == "__main__":
    main()