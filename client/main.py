import requests
from typing import Optional, Dict, Any
import json

class ChordFinderClient:
    """Клиент для работы с API сервера"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.session = requests.Session()
    
    def _request(self, method: str, endpoint: str, 
                  data: Optional[Dict] = None, 
                  params: Optional[Dict] = None,
                  need_auth: bool = False) -> Dict:
        """
        Базовый метод для отправки запросов
        """
        url = f"{self.base_url}{endpoint}"
        headers = {}
        
        # Добавляем токен авторизации, если нужно
        if need_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        try:
            if method == "GET":
                response = self.session.get(url, params=params, headers=headers)
            elif method == "POST":
                response = self.session.post(url, json=data, headers=headers)
            else:
                raise ValueError(f"Неподдерживаемый метод: {method}")
            
            # Проверяем статус ответа
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.ConnectionError:
            print("Ошибка: Не удалось подключиться к серверу")
            print("   Убедитесь, что сервер запущен (python server.py)")
            return {}
        except requests.exceptions.HTTPError as e:
            print(f"HTTP ошибка: {e}")
            if response.status_code == 401:
                print("   Требуется авторизация")
            elif response.status_code == 404:
                print("   Ресурс не найден")
            return {}
        except Exception as e:
            print(f"Неизвестная ошибка: {e}")
            return {}
    
    # --- МЕТОДЫ ДЛЯ РАБОТЫ С API ---
    
    def check_connection(self) -> bool:
        """Проверка связи с сервером"""
        result = self._request("GET", "/")
        return result.get("status") == "ok"
    
    def get_all_songs(self) -> list:
        """Получить все песни"""
        return self._request("GET", "/songs")
    
    def get_song(self, song_id: int) -> Dict:
        """Получить песню по ID"""
        return self._request("GET", f"/songs/{song_id}")
    
    def search_songs(self, query: str) -> list:
        """Поиск песен"""
        return self._request("POST", "/search", data={"query": query})
    
    def add_song(self, title: str, artist: str, 
                  text: str = "", chords: list = None) -> Dict:
        """Добавить новую песню"""
        song_data = {
            "title": title,
            "artist": artist,
            "text": text,
            "chords": chords or []
        }
        return self._request("POST", "/songs", data=song_data)
    
    def login(self, username: str, password: str) -> bool:
        """Авторизация на сервере"""
        result = self._request("POST", "/login", 
                               data={"username": username, 
                                     "password": password})
        if result.get("access_token"):
            self.token = result["access_token"]
            print(f"✅ Успешный вход как {username}")
            return True
        return False
    
    def get_protected_data(self) -> Dict:
        """Получить защищенные данные (требуется авторизация)"""
        if not self.token:
            print("Требуется авторизация")
            return {}
        
        return self._request("GET", f"/protected?token={self.token}", 
                              need_auth=True)


def menu():
    client = ChordFinderClient()
    
    if not client.check_connection():
        print("Сервер не запущен!")
        return
    
    while True:
        print("\n" + "="*30)
        print("МЕНЮ:")
        print("1. Поиск песен")
        print("2. Показать все песни")
        print("3. Добавить песню")
        print("4. Выйти")
        
        choice = input("\nВыберите действие (1-4): ")
        
        if choice == "1":
            query = input("Введите название или исполнителя: ")
            results = client.search_songs(query)
            print(f"\nНайдено песен: {len(results)}")
            for song in results:
                print(f"  {song['artist']} - {song['title']}")
                
        elif choice == "2":
            songs = client.get_all_songs()
            print(f"\nВсего песен: {len(songs)}")
            for song in songs:
                print(f"  {song['artist']} - {song['title']}")
                
        elif choice == "3":
            artist = input("Исполнитель: ")
            title = input("Название: ")
            chords = input("Аккорды (через пробел): ").split()
            
            new_song = client.add_song(title, artist, chords=chords)
            if new_song:
                print(f"Песня добавлена с ID: {new_song.get('id')}")
                
        elif choice == "4":
            break


if __name__ == "__main__":
    menu()