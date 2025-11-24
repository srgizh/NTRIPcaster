#!/usr/bin/env python3
"""
Скрипт массового добавления пользователей для тестирования
Функция: добавление 500 тестовых пользователей через Web API
"""

import requests
import json
import time
import sys

# Конфигурация сервера
WEB_SERVER_URL = "http://192.168.1.4:5757"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

def login_admin():
    """Вход администратора"""
    login_url = f"{WEB_SERVER_URL}/api/login"
    login_data = {
        "username": ADMIN_USERNAME,
        "password": ADMIN_PASSWORD
    }
    
    try:
        response = requests.post(login_url, json=login_data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"Вход администратора успешен: {ADMIN_USERNAME}")
                return response.cookies
            else:
                print(f"Ошибка входа: {result.get('message', 'Неизвестная ошибка')}")
                return None
        else:
            print(f"Запрос входа не удался, код состояния: {response.status_code}")
            return None
    except Exception as e:
        print(f"Исключение при входе: {e}")
        return None

def add_user(cookies, username, password):
    """Добавление одного пользователя"""
    add_user_url = f"{WEB_SERVER_URL}/api/users"
    user_data = {
        "username": username,
        "password": password
    }
    
    try:
        response = requests.post(add_user_url, json=user_data, cookies=cookies, timeout=10)
        if response.status_code in [200, 201]:  # Принимаются коды состояния 200 и 201
            result = response.json()
            return result.get('success', False), result.get('message', '')
        else:
            return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)

def main():
    """Главная функция"""
    print("Начало массового добавления пользователей для тестирования...")
    print(f"Целевой сервер: {WEB_SERVER_URL}")
    print(f"Учетная запись администратора: {ADMIN_USERNAME}")
    print("="*50)
    
    # Вход администратора
    cookies = login_admin()
    if not cookies:
        print("Вход администратора не удался, выход из программы")
        sys.exit(1)
    
    # Массовое добавление пользователей
    total_users = 500
    success_count = 0
    failed_count = 0
    
    print(f"Начало добавления {total_users} пользователей...")
    start_time = time.time()
    
    for i in range(1, total_users + 1):
        # Генерация последовательных имен пользователей и паролей
        username = f"testuser{i:03d}"  # testuser001, testuser002, ..., testuser500
        password = f"pass{i:03d}"      # pass001, pass002, ..., pass500
        
        success, message = add_user(cookies, username, password)
        
        if success:
            success_count += 1
            if i % 50 == 0:  # Показывать прогресс каждые 50 пользователей
                print(f"Успешно добавлено {success_count} пользователей (прогресс: {i}/{total_users})")
        else:
            failed_count += 1
            print(f"Ошибка добавления пользователя {username}: {message}")
        
        # Избежание слишком частых запросов
        time.sleep(0.01)
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    print("="*50)
    print("Добавление пользователей завершено!")
    print(f"Всего пользователей: {total_users}")
    print(f"Успешно добавлено: {success_count}")
    print(f"Не удалось добавить: {failed_count}")
    print(f"Затрачено времени: {elapsed_time:.2f} сек")
    print(f"Средняя скорость: {total_users/elapsed_time:.2f} пользователей/сек")
    
    # Сохранение информации о пользователях в файл для использования в тестах NTRIP
    user_list = []
    for i in range(1, total_users + 1):
        user_list.append({
            "username": f"testuser{i:03d}",
            "password": f"pass{i:03d}"
        })
    
    with open("test_users.json", "w", encoding="utf-8") as f:
        json.dump(user_list, f, indent=2, ensure_ascii=False)
    
    print(f"Информация о пользователях сохранена в файл test_users.json")

if __name__ == "__main__":
    main()