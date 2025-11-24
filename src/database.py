#!/usr/bin/env python3

import sqlite3
import hashlib
import secrets
import logging
from threading import Lock
from . import config
from . import logger
from .logger import log_debug, log_info, log_warning, log_error, log_critical, log_database_operation, log_authentication

db_lock = Lock()


def hash_password(password, salt=None):
    """Хеширование пароля с использованием PBKDF2 и SHA256"""
    if salt is None:
        salt = secrets.token_hex(16)  
    
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 10000)
    return f"{salt}${key.hex()}"

def verify_password(stored_password, provided_password):
    """Проверка соответствия пароля"""
    
    if '$' not in stored_password:
       
        return stored_password == provided_password
        
    salt, hash_value = stored_password.split('$', 1)
    
    key = hashlib.pbkdf2_hmac('sha256', provided_password.encode(), salt.encode(), 10000)
    
    return key.hex() == hash_value

def init_db():
    """Инициализация структуры таблиц SQLite базы данных"""
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()

        # Таблица администраторов
        c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
        ''')
        
        # Таблица пользователей (пользователи NTRIP клиентов)
        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
        ''')
        
        # Таблица точек монтирования
        c.execute('''
        CREATE TABLE IF NOT EXISTS mounts (
            id INTEGER PRIMARY KEY,
            mount TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE SET NULL
                ON UPDATE CASCADE
        )
        ''')
        
        c.execute("SELECT * FROM admins")
        if not c.fetchone():
            # Использование хешированного пароля для хранения пароля администратора по умолчанию
            admin_username = config.DEFAULT_ADMIN['username']
            admin_password = config.DEFAULT_ADMIN['password']
            hashed_password = hash_password(admin_password)
            c.execute("INSERT INTO admins (username, password) VALUES (?, ?)", (admin_username, hashed_password))
            print(f"Создан администратор по умолчанию: {admin_username}/{admin_password}（пожалуйста, измените пароль при первом входе）")
        
        conn.commit()
        conn.close()
        log_info('Инициализация базы данных завершена')

def verify_mount_and_user(mount, username=None, password=None, mount_password=None, protocol_version="1.0"):
    """Проверка валидности точки монтирования и информации о пользователе
    
    Args:
        mount: Имя точки монтирования
        username: Имя пользователя (необязательно)
        password: Пароль пользователя (необязательно)
        mount_password: Пароль точки монтирования (необязательно)
    """
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        
        try:
            # Проверка существования точки монтирования и получение связанной информации
            c.execute("SELECT id, password, user_id FROM mounts WHERE mount = ?", (mount,))
            mount_result = c.fetchone()
            
            if not mount_result:
                log_authentication(username or 'unknown', mount, False, 'database', 'Точка монтирования не существует')
                return False, "Точка монтирования не существует"
            
            mount_id, stored_mount_password, bound_user_id = mount_result
            
            # Различная логика проверки в зависимости от версии протокола
            if protocol_version == "2.0":
                
                if not username or not password:
                    log_authentication(username or 'unknown', mount, False, 'database', 'NTRIP 2.0 требует имя пользователя и пароль')
                    return False, "Протокол NTRIP 2.0 требует указание имени пользователя и пароля"
                
                # Проверка существования пользователя
                c.execute("SELECT id, password FROM users WHERE username = ?", (username,))
                user_result = c.fetchone()
                if not user_result:
                    log_authentication(username, mount, False, 'database', 'Пользователь не существует')
                    return False, "Пользователь не существует"
                
                user_id, stored_user_password = user_result
                
                # Проверка пароля пользователя
                if not verify_password(stored_user_password, password):
                    log_authentication(username, mount, False, 'database', 'Неверный пароль пользователя')
                    return False, "Неверный пароль пользователя"
                
                # Проверка привязки точки монтирования к пользователю
                if bound_user_id is not None and bound_user_id != user_id:
                    log_authentication(username, mount, False, 'database', 'У пользователя нет прав доступа к этой точке монтирования')
                    return False, "У пользователя нет прав доступа к этой точке монтирования"
                
                # NTRIP 2.0 не проверяет пароль точки монтирования, только имя пользователя и пароль, а также права на точку монтирования
                log_authentication(username, mount, True, 'database', 'Аутентификация NTRIP 2.0 успешна')
                return True, "Аутентификация NTRIP 2.0 успешна"
            
            else:
                # Логика проверки для NTRIP 1.0 и более старых версий
                if not mount_password:
                    log_authentication(username or 'unknown', mount, False, 'database', 'NTRIP 1.0 требует пароль точки монтирования')
                    return False, "Протокол NTRIP 1.0 требует указание пароля точки монтирования"
                
                # Проверка пароля точки монтирования
                if stored_mount_password != mount_password:
                    log_authentication(username or 'unknown', mount, False, 'database', 'Неверный пароль точки монтирования')
                    return False, "Неверный пароль точки монтирования"
                
                # NTRIP 1.0 проверяет только точку монтирования и пароль точки монтирования, не проверяет пользователя
                log_authentication(username or 'unknown', mount, True, 'database', 'Аутентификация NTRIP 1.0 успешна')
                return True, "Аутентификация NTRIP 1.0 успешна"
            
        except Exception as e:
            log_error(f"Ошибка аутентификации пользователя: {e}", exc_info=True)
            return False, f"Ошибка аутентификации: {e}"
        finally:
            conn.close()



def add_user(username, password):
    """Добавление нового пользователя в базу данных"""
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        try:
            # Проверка существования пользователя
            c.execute("SELECT * FROM users WHERE username = ?", (username,))
            if c.fetchone():
                return False, "Имя пользователя уже существует"
            
            # Хеширование пароля и добавление пользователя
            hashed_password = hash_password(password)
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            conn.commit()
            log_database_operation('add_user', 'users', True, f'Пользователь: {username}')
            return True, "Пользователь успешно добавлен"
        except Exception as e:
            log_database_operation('add_user', 'users', False, str(e))
            return False, f"Ошибка при добавлении пользователя: {e}"
        finally:
            conn.close()

def update_user(user_id, username, password):
    """Обновление информации о пользователе"""
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        try:
            # Проверка конфликта имени пользователя с другими пользователями
            c.execute("SELECT * FROM users WHERE username = ? AND id != ?", (username, user_id))
            if c.fetchone():
                return False, "Имя пользователя уже существует"
            
            c.execute("SELECT password FROM users WHERE id = ?", (user_id,))
            old_password = c.fetchone()[0]
            
            if '$' in old_password and verify_password(old_password, password):
                new_password = old_password
            else:
                new_password = hash_password(password)
            
            c.execute("UPDATE users SET username = ?, password = ? WHERE id = ?", (username, new_password, user_id))
            conn.commit()
            log_database_operation('update_user', 'users', True, f'Пользователь: {username}')
            return True, "Информация о пользователе успешно обновлена"
        except Exception as e:
            log_database_operation('update_user', 'users', False, str(e))
            return False, f"Ошибка при обновлении пользователя: {e}"
        finally:
            conn.close()

def delete_user(user_id):
    """Удаление пользователя"""
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        try:
            
            c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
            result = c.fetchone()
            if not result:
                return False, "Пользователь не существует"
            
            username = result[0]
            
            # Сначала очистить user_id всех точек монтирования, привязанных к этому пользователю
            c.execute("UPDATE mounts SET user_id = NULL WHERE user_id = ?", (user_id,))
            affected_mounts = c.rowcount
            
            # Удаление пользователя
            c.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            
            log_message = f'Пользователь: {username}'
            if affected_mounts > 0:
                log_message += f', одновременно очищена привязка пользователя в {affected_mounts} точках монтирования'
            
            log_database_operation('delete_user', 'users', True, log_message)
            return True, username
        except Exception as e:
            log_database_operation('delete_user', 'users', False, str(e))
            return False, f"Ошибка при удалении пользователя: {e}"
        finally:
            conn.close()

def get_all_users():
    """Получение списка всех пользователей"""
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        try:
            c.execute("SELECT id, username, password FROM users")
            return c.fetchall()
        finally:
            conn.close()

def update_user_password(username, new_password):
    """Обновление пароля пользователя"""
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        try:
            
            c.execute("SELECT id FROM users WHERE username = ?", (username,))
            result = c.fetchone()
            if not result:
                return False, "Пользователь не существует"
            
            
            hashed_password = hash_password(new_password)
            
            c.execute("UPDATE users SET password = ? WHERE username = ?", (hashed_password, username))
            conn.commit()
            log_info(f"Пароль пользователя {username} успешно обновлен")
            return True, "Пароль успешно обновлен"
        except Exception as e:
            log_error(f"Ошибка при обновлении пароля пользователя: {e}")
            return False, f"Ошибка при обновлении пароля: {e}"
        finally:
            conn.close()

def add_mount(mount, password, user_id=None):
    """Добавление новой точки монтирования"""
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        try:
           
            c.execute("SELECT * FROM mounts WHERE mount = ?", (mount,))
            if c.fetchone():
                return False, "Имя точки монтирования уже существует"
            
            # Если указан ID пользователя, проверяем существование пользователя
            if user_id is not None:
                c.execute("SELECT id FROM users WHERE id = ?", (user_id,))
                if not c.fetchone():
                    return False, "Указанный пользователь не существует"
            
            c.execute("INSERT INTO mounts (mount, password, user_id) VALUES (?, ?, ?)", (mount, password, user_id))
            conn.commit()
            log_database_operation('add_mount', 'mounts', True, f'Точка монтирования: {mount}, ID пользователя: {user_id}')
            return True, "Точка монтирования успешно добавлена"
        except Exception as e:
            log_database_operation('add_mount', 'mounts', False, str(e))
            return False, f"Ошибка при добавлении точки монтирования: {e}"
        finally:
            conn.close()

def update_mount(mount_id, mount=None, password=None, user_id=None):
    """Обновление информации о точке монтирования"""
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        try:
            
            c.execute("SELECT mount, password, user_id FROM mounts WHERE id = ?", (mount_id,))
            result = c.fetchone()
            if not result:
                return False, "Точка монтирования не существует"
            
            old_mount, old_password, old_user_id = result
            
            
            new_mount = mount if mount is not None else old_mount
            new_password = password if password is not None else old_password
            new_user_id = user_id if user_id != 'keep_current' else old_user_id
            
            # Проверка конфликта имени точки монтирования с другими точками монтирования
            if mount is not None and mount != old_mount:
                c.execute("SELECT * FROM mounts WHERE mount = ? AND id != ?", (mount, mount_id))
                if c.fetchone():
                    return False, "Имя точки монтирования уже существует"
            # Если указан ID пользователя, проверяем существование пользователя
            if new_user_id is not None:
                c.execute("SELECT id FROM users WHERE id = ?", (new_user_id,))
                if not c.fetchone():
                    return False, "Указанный пользователь не существует"
            
            c.execute("UPDATE mounts SET mount = ?, password = ?, user_id = ? WHERE id = ?", (new_mount, new_password, new_user_id, mount_id))
            conn.commit()
            log_database_operation('update_mount', 'mounts', True, f'Точка монтирования: {old_mount} -> {new_mount}')
            return True, old_mount
        except Exception as e:
            log_database_operation('update_mount', 'mounts', False, str(e))
            return False, f"Ошибка при обновлении точки монтирования: {e}"
        finally:
            conn.close()

def delete_mount(mount_id):
    """Удаление точки монтирования"""
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        try:
            
            c.execute("SELECT mount FROM mounts WHERE id = ?", (mount_id,))
            result = c.fetchone()
            if not result:
                return False, "Точка монтирования не существует"
            
            mount = result[0]
            c.execute("DELETE FROM mounts WHERE id = ?", (mount_id,))
            conn.commit()
            log_database_operation('delete_mount', 'mounts', True, f'Точка монтирования: {mount}')
            return True, mount
        except Exception as e:
            logger.log_database_operation('delete_mount', 'mounts', False, str(e))
            return False, f"Ошибка при удалении точки монтирования: {e}"
        finally:
            conn.close()

def get_all_mounts():
    """Получение списка всех точек монтирования"""
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        try:
            c.execute("PRAGMA table_info(mounts)")
            columns = [column[1] for column in c.fetchall()]
            
            if 'lat' in columns and 'lon' in columns:
                c.execute("""SELECT m.id, m.mount, m.password, m.user_id, u.username, m.lat, m.lon
                             FROM mounts m 
                             LEFT JOIN users u ON m.user_id = u.id""")
            else:
                c.execute("""SELECT m.id, m.mount, m.password, m.user_id, u.username, NULL as lat, NULL as lon
                             FROM mounts m 
                             LEFT JOIN users u ON m.user_id = u.id""")
            return c.fetchall()
        finally:
            conn.close()


def verify_admin(username, password):
    """Проверка имени пользователя и пароля администратора"""
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        try:
            c.execute("SELECT password FROM admins WHERE username = ?", (username,))
            result = c.fetchone()
            if result and verify_password(result[0], password):
                return True
            return False
        finally:
            conn.close()

def update_admin_password(username, new_password):
    """Обновление пароля администратора"""
    with db_lock:
        conn = sqlite3.connect(config.DATABASE_PATH)
        c = conn.cursor()
        try:
            hashed_password = hash_password(new_password)
            c.execute("UPDATE admins SET password = ? WHERE username = ?", (hashed_password, username))
            conn.commit()
            log_database_operation('update_admin_password', 'admins', True, f'Администратор: {username}')
            return True
        except Exception as e:
            log_database_operation('update_admin_password', 'admins', False, str(e))
            return False
        finally:
            conn.close()


class DatabaseManager:
    """Класс менеджера базы данных, обертка для функций работы с базой данных"""
    
    def __init__(self):
        """Инициализация менеджера базы данных"""
        pass
    
    def init_database(self):
        """Инициализация базы данных"""
        return init_db()
    
    def verify_mount_and_user(self, mount, username=None, password=None, mount_password=None, protocol_version="1.0"):
        """Проверка точки монтирования и пользователя"""
        return verify_mount_and_user(mount, username, password, mount_password, protocol_version)
    
    def add_user(self, username, password):
        """Добавление пользователя"""
        return add_user(username, password)
    
    def update_user_password(self, username, new_password):
        """Обновление пароля пользователя"""
        return update_user_password(username, new_password)
    
    def delete_user(self, username):
        """Удаление пользователя"""
        users = get_all_users()
        user_id = None
        for user in users:
            if user[1] == username:  # user[1] это username
                user_id = user[0]    # user[0] это id
                break
        
        if user_id is None:
            return False, "Пользователь не существует"
        
        return delete_user(user_id)
    
    def get_all_users(self):
        """Получение всех пользователей"""
        return get_all_users()
    
    def get_user_password(self, username):
        """Получение пароля пользователя для Digest-аутентификации"""
        with sqlite3.connect(config.DATABASE_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT password FROM users WHERE username = ?", (username,))
            result = c.fetchone()
            return result[0] if result else None
    
    def check_mount_exists_in_db(self, mount):
        """Проверка существования точки монтирования в базе данных"""
        with sqlite3.connect(config.DATABASE_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM mounts WHERE mount = ?", (mount,))
            return c.fetchone() is not None
    
    def verify_download_user(self, mount, username, password):
        """Проверка пользователя для загрузки, проверяется только имя пользователя и пароль, не проверяется привязка точки монтирования"""
        with sqlite3.connect(config.DATABASE_PATH) as conn:
            c = conn.cursor()
            
            c.execute("SELECT id FROM mounts WHERE mount = ?", (mount,))
            mount_result = c.fetchone()
            if not mount_result:
                logger.log_authentication(username, mount, False, 'database', 'Точка монтирования не существует')
                return False, "Точка монтирования не существует"
            
            c.execute("SELECT id, password FROM users WHERE username = ?", (username,))
            user_result = c.fetchone()
            if not user_result:
                logger.log_authentication(username, mount, False, 'database', 'Пользователь не существует')
                return False, "Пользователь не существует"
            
            user_id, stored_password = user_result
            
            if not verify_password(stored_password, password):
                logger.log_authentication(username, mount, False, 'database', 'Неверный пароль пользователя')
                return False, "Неверный пароль пользователя"
            
           
            logger.log_authentication(username, mount, True, 'database', 'Аутентификация для загрузки успешна')
            return True, "Аутентификация для загрузки успешна"
    
    def add_mount(self, mount, password=None, user_id=None):
        """Добавление точки монтирования"""
        return add_mount(mount, password, user_id)
    
    def update_mount_password(self, mount, new_password):
        """Обновление пароля точки монтирования"""
        with db_lock:
            conn = sqlite3.connect(config.DATABASE_PATH)
            c = conn.cursor()
            try:
                c.execute("UPDATE mounts SET password = ? WHERE mount = ?", (new_password, mount))
                if c.rowcount > 0:
                    conn.commit()
                    return True, "Пароль точки монтирования успешно обновлен"
                else:
                    return False, "Точка монтирования не существует"
            except Exception as e:
                return False, f"Ошибка при обновлении пароля точки монтирования: {str(e)}"
            finally:
                conn.close()
    
    def update_user(self, user_id, username, password):
        """Обновление информации о пользователе"""
        return update_user(user_id, username, password)
    
    def update_mount(self, mount_id, mount=None, password=None, user_id=None):
        """Обновление информации о точке монтирования"""
        return update_mount(mount_id, mount, password, user_id)
    
    def delete_mount(self, mount):
        """Удаление точки монтирования"""
        mounts = self.get_all_mounts()
        mount_id = None
        for m in mounts:
            if m[1] == mount:  # m[1] это имя точки монтирования
                mount_id = m[0]  # m[0] это ID
                break
        
        if mount_id is None:
            return False, "Точка монтирования не существует"
        
        return delete_mount(mount_id)
    
    def get_all_mounts(self):
        """Получение всех точек монтирования"""
        return get_all_mounts()
       
    def verify_admin(self, username, password):
        """Проверка администратора"""
        return verify_admin(username, password)
    
    def update_admin_password(self, username, new_password):
        """Обновление пароля администратора"""
        return update_admin_password(username, new_password)
    
