#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт проверки работоспособности NTRIP Caster
Для проверки здоровья Docker-контейнера и мониторинга
"""

import sys
import time
import socket
import urllib.request
import urllib.error
import json
import logging
from typing import Dict, List, Tuple, Optional
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HealthChecker:
    """Проверка работоспособности"""
    
    def __init__(self):
        self.checks = [
            self.check_web_service,
            self.check_ntrip_service,
            self.check_memory_usage,
            self.check_disk_space,
        ]
    
    def check_web_service(self) -> Tuple[bool, str]:
        """Проверка веб-сервиса"""
        try:
            with urllib.request.urlopen('http://localhost:5757/health', timeout=5) as response:
                if response.status == 200:
                    return True, "Веб-сервис работает нормально"
                else:
                    return False, f"Веб-сервис вернул код состояния: {response.status}"
        except urllib.error.URLError as e:
            return False, f"Ошибка подключения к веб-сервису: {e}"
        except Exception as e:
            return False, f"Исключение при проверке веб-сервиса: {e}"
    
    def check_ntrip_service(self) -> Tuple[bool, str]:
        """Проверка порта NTRIP-сервиса"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(('localhost', 2101))
            sock.close()
            
            if result == 0:
                return True, "Порт NTRIP-сервиса работает нормально"
            else:
                return False, "Не удалось подключиться к порту NTRIP-сервиса"
        except Exception as e:
            return False, f"Исключение при проверке NTRIP-сервиса: {e}"
    
    def check_memory_usage(self) -> Tuple[bool, str]:
        """Проверка использования памяти"""
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
            
            mem_total = 0
            mem_available = 0
            
            for line in meminfo.split('\n'):
                if line.startswith('MemTotal:'):
                    mem_total = int(line.split()[1]) * 1024  # Преобразование в байты
                elif line.startswith('MemAvailable:'):
                    mem_available = int(line.split()[1]) * 1024  # Преобразование в байты
            
            if mem_total > 0:
                usage_percent = (mem_total - mem_available) / mem_total * 100
                if usage_percent < 90:
                    return True, f"Использование памяти: {usage_percent:.1f}%"
                else:
                    return False, f"Слишком высокое использование памяти: {usage_percent:.1f}%"
            else:
                return False, "Не удалось получить информацию о памяти"
        except Exception as e:
            return False, f"Исключение при проверке памяти: {e}"
    
    def check_disk_space(self) -> Tuple[bool, str]:
        """Проверка дискового пространства"""
        try:
            import shutil
            total, used, free = shutil.disk_usage('/app')
            usage_percent = used / total * 100
            
            if usage_percent < 90:
                return True, f"Использование диска: {usage_percent:.1f}%"
            else:
                return False, f"Недостаточно дискового пространства: {usage_percent:.1f}%"
        except Exception as e:
            return False, f"Исключение при проверке диска: {e}"
    
    def run_checks(self) -> Dict[str, any]:
        """Запуск всех проверок работоспособности"""
        results = {
            'healthy': True,
            'timestamp': time.time(),
            'checks': {},
            'summary': ''
        }
        
        failed_checks = []
        
        for check in self.checks:
            check_name = check.__name__.replace('check_', '')
            try:
                success, message = check()
                results['checks'][check_name] = {
                    'success': success,
                    'message': message
                }
                
                if success:
                    logger.info(f"[OK] {check_name}: {message}")
                else:
                    logger.error(f"[FAIL] {check_name}: {message}")
                    failed_checks.append(check_name)
                    results['healthy'] = False
            except Exception as e:
                logger.error(f"[ERROR] {check_name}: Проверка не удалась - {e}")
                results['checks'][check_name] = {
                    'success': False,
                    'message': f"Проверка не удалась: {e}"
                }
                failed_checks.append(check_name)
                results['healthy'] = False
        
        if results['healthy']:
            results['summary'] = "Все проверки работоспособности пройдены"
            logger.info("[OK] Все проверки работоспособности пройдены")
        else:
            results['summary'] = f"Проверки работоспособности не пройдены: {', '.join(failed_checks)}"
            logger.error(f"[FAIL] Проверки работоспособности не пройдены: {', '.join(failed_checks)}")
        
        return results


def main():
    """Главная функция"""
    checker = HealthChecker()
    results = checker.run_checks()
    
    # Вывод результатов в формате JSON (для систем мониторинга)
    if '--json' in sys.argv:
        print(json.dumps(results, indent=2))
    
    # Установка кода выхода в зависимости от состояния работоспособности
    if results['healthy']:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()