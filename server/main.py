from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import uvicorn

# Создаем приложение
app = FastAPI(title="ChordFinder API")

# Разрешаем запросы с любого источника (для разработки)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- МОДЕЛИ ДАННЫХ ---
class Song(BaseModel):
    """Модель песни"""
    id: Optional[int] = None
    title: str
    artist: str
    text: Optional[str] = None
    chords: Optional[List[str]] = None
    
class SearchQuery(BaseModel):
    """Модель поискового запроса"""
    query: str
    
class User(BaseModel):
    """Модель пользователя"""
    username: str
    password: str
    
class Token(BaseModel):
    """Модель токена"""
    access_token: str
    token_type: str

# --- ВРЕМЕННАЯ БАЗА ДАННЫХ (В ПАМЯТИ) ---
# В реальном проекте замените на настоящую БД
songs_db = [
    Song(id=1, title="Кукушка", artist="Кино", 
         text="Куплет: ...", chords=["Am", "C", "G"]),
    Song(id=2, title="Восьмиклассница", artist="Кино",
         text="Текст песни...", chords=["Am", "Em", "C", "G"]),
    Song(id=3, title="Хочешь", artist="Земфира",
         text="Текст...", chords=["Am", "F", "G"]),
]

# Простая авторизация (для примера)
users_db = {
    "user": "password123",
    "admin": "admin123"
}

# --- API ЭНДПОИНТЫ ---

@app.get("/")
def root():
    return {"message": "ChordFinder API работает!", "status": "ok"}

@app.get("/songs", response_model=List[Song])
def get_all_songs():
    """Получить все песни"""
    return songs_db

@app.get("/songs/{song_id}", response_model=Song)
def get_song(song_id: int):
    """Получить песню по ID"""
    for song in songs_db:
        if song.id == song_id:
            return song
    raise HTTPException(status_code=404, detail="Песня не найдена")

@app.post("/search", response_model=List[Song])
def search_songs(query: SearchQuery):
    """Поиск песен по названию или исполнителю"""
    results = []
    search_lower = query.query.lower()
    
    for song in songs_db:
        if (search_lower in song.title.lower() or 
            search_lower in song.artist.lower()):
            results.append(song)
    
    return results

@app.post("/songs", response_model=Song)
def create_song(song: Song):
    """Добавить новую песню"""
    # Генерируем новый ID
    new_id = max([s.id for s in songs_db]) + 1 if songs_db else 1
    song.id = new_id
    songs_db.append(song)
    return song

@app.post("/login")
def login(user: User):
    """Простая авторизация"""
    if user.username in users_db and users_db[user.username] == user.password:
        return {
            "access_token": f"fake-token-{user.username}",
            "token_type": "bearer"
        }
    raise HTTPException(status_code=401, detail="Неверный логин или пароль")

@app.get("/protected")
def protected_page(token: str):
    raise HTTPException(status_code=401, detail="Не авторизован")

# Запуск сервера
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
    print("Сервер запущен на http://127.0.0.1:8000")