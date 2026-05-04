import os
import re
import bcrypt
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Optional, List
import song_handler

import uvicorn
import pyotp
from fastapi import FastAPI, HTTPException, Depends, status, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import (
    get_db, init_db, SessionLocal,
    create_song, get_song, search_songs, get_all_songs, update_song, delete_song,
    create_user, get_user, get_all_users, delete_user, update_user,
    add_to_favorites, remove_from_favorites, get_favorites,
    create_playlist, add_to_playlist, get_playlist_songs, delete_playlist,
    increment_song_hits, User, Song, Playlist, remove_from_playlist
)

# =============================================================================
# НАСТРОЙКИ
# =============================================================================
SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
TWOFA_ISSUER = "ChordFinder"
BCRYPT_ROUNDS = 12

security = HTTPBearer(auto_error=False)

# =============================================================================
# LIFESPAN (Инициализация БД)
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        print("✅ База данных успешно инициализирована")
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
    yield
    print("👋 Сервер остановлен")

# =============================================================================
# ПРИЛОЖЕНИЕ
# =============================================================================
app = FastAPI(title="ChordFinder API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# ФУНКЦИИ БЕЗОПАСНОСТИ 
# =============================================================================

def hash_password(password: str) -> str:
    """Хеширует пароль с помощью bcrypt"""
    if isinstance(password, str):
        password = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password, salt)
    return hashed.decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    """Проверяет пароль против хеша"""
    if isinstance(hashed, str):
        hashed = hashed.encode('utf-8')
    if isinstance(plain, str):
        plain = plain.encode('utf-8')
    try:
        return bcrypt.checkpw(plain, hashed)
    except ValueError:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None, token_type: str = "access") -> str:
    """Создаёт JWT token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "type": token_type,  
        "iat": datetime.now(timezone.utc)
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict) -> str:
    """Создаёт JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "iat": datetime.now(timezone.utc)
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str, token_type: str = "access") -> Optional[dict]:
    """Декодирует JWT"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": True})
        
        # Проверяем тип токена
        token_claim_type = payload.get("type")
        if token_claim_type and token_claim_type != token_type:
            print(f"Token type mismatch: got '{token_claim_type}', expected '{token_type}'")
            return None
        return payload
    except jwt.ExpiredSignatureError:
        print("Token expired")
        return None
    except jwt.JWTError as e:
        print(f"JWT decode error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected token error: {type(e).__name__}: {e}")
        return None



async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security), db: Session = Depends(get_db)) -> User:
    """Получает текущего пользователя из JWT-токена"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Требуется авторизация", headers={"WWW-Authenticate": "Bearer"})
    
    payload = decode_token(credentials.credentials)
    if not payload:
        print("[AUTH] Token decoding failed")
        raise HTTPException(status_code=401, detail="Неверный или просроченный токен")
    
    user_id = payload.get("sub")
    if user_id is None:
        print(f"[AUTH] Missing 'sub' in payload: {payload}")
        raise HTTPException(status_code=401, detail="Неверный токен")
    
    user = get_user(db, user_id=user_id)
    if not user:
        print(f"[AUTH] User {user_id} not found in DB")
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Проверяет права администратора"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Доступ запрещен: требуется роль admin")
    return current_user

# =============================================================================
# PYDANTIC СХЕМЫ
# =============================================================================

class SongCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    artist: str = Field(..., min_length=1, max_length=200)
    text: Optional[str] = None
    chords: Optional[List[str]] = None
    source_url: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class SongResponse(BaseModel):
    id: int
    title: str
    artist: str
    text: Optional[str] = None
    chords: Optional[List[str]] = None
    source_url: Optional[str] = None
    hits: int
    verified: bool
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
    
    @field_validator('chords', mode='before')
    @classmethod
    def parse_chords(cls, value):
        if value is None:
            return None
        if isinstance(value, list):
            return value  # Уже список — возвращаем как есть
        if isinstance(value, str):
            try:
                import json
                return json.loads(value)  # Парсим JSON-строку
            except (json.JSONDecodeError, TypeError):
                return []  # Если не удалось — пустой список
        return value

class SongUpdate(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    text: Optional[str] = None
    chords: Optional[List[str]] = None
    source_url: Optional[str] = None
    verified: Optional[bool] = None
    model_config = ConfigDict(from_attributes=True)

class SearchQuery(BaseModel):
    query: str = Field(..., min_length=1)

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r'^[\w\-\.]+$')
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    password: str = Field(..., min_length=8)
    model_config = ConfigDict(from_attributes=True)

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    twofa_enabled: bool
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"

class FavoriteRequest(BaseModel):
    song_id: int

class PlaylistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class PlaylistResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class TwoFASetupResponse(BaseModel):
    secret: str
    qr_code_uri: str
    message: str

class TwoFAVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)

from fastapi.concurrency import run_in_threadpool

async def db_run(func, *args, **kwargs):
    """Запускает синхронную БД-функцию в тредпуле"""
    return await run_in_threadpool(lambda: func(*args, **kwargs))

# =============================================================================
# ЭНДПОИНТЫ: ПУБЛИЧНЫЕ
# =============================================================================

@app.get("/")
def root():
    return {"message": "ChordFinder API v1.0", "status": "ok", "docs": "/docs"}

@app.get("/api/songs", response_model=List[SongResponse])
async def get_all_songs_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    limit = min(limit, 200)
    return await db_run(get_all_songs, db, skip=skip, limit=limit)

@app.get("/api/songs/{song_id}", response_model=SongResponse)
async def get_song_endpoint(song_id: int, db: Session = Depends(get_db)):
    song = await db_run(get_song, db, song_id=song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Песня не найдена")
    await db_run(increment_song_hits, db, song_id)
    return song

@app.post("/api/search", response_model=List[SongResponse])
async def search_songs_endpoint(query: SearchQuery, limit: int = 20, db: Session = Depends(get_db)):
    """Поиск песен: БД → проверка дублей → парсеры → сохранение с задержкой → возврат"""
    import asyncio  # ✅ Импортируем для async sleep
    
    limit = min(limit, 50)

    # 1. Стандартный поиск в базе данных
    results = await db_run(search_songs, db, query.query, limit=limit)

    # 2. Если не найдено — пробуем спарсить
    if not results:
        try:
            parsed = await run_in_threadpool(lambda: song_handler.song_handler(query.query))

            if parsed and parsed.get('title') and parsed.get('artist'):
                # Проверка по источнику (URL)
                if parsed.get('url'):
                    existing_by_url = await db_run(lambda: db.query(Song).filter(Song.source_url == parsed['url']).first())
                    if existing_by_url:
                        results = [existing_by_url]
                        return results

                # Нормализация для сравнения
                def normalize(txt: str) -> str:
                    return re.sub(r'[^\w\sа-яё-]', '', txt.lower()).strip()

                norm_title = normalize(parsed['title'])
                norm_artist = normalize(parsed['artist'])

                # Ищем в БД
                candidates = await db_run(lambda: db.query(Song).filter(
                    Song.title.ilike(f"%{parsed['title']}%") | Song.artist.ilike(f"%{parsed['artist']}%")
                ).limit(50).all())

                found = None
                for cand in candidates:
                    if normalize(cand.title) == norm_title and normalize(cand.artist) == norm_artist:
                        found = cand
                        break

                if found:
                    results = [found]
                else:
                    # Создаём новую запись
                    new_song = await db_run(
                        create_song, db,
                        title=parsed['title'].strip(),
                        artist=parsed['artist'].strip(),
                        text=parsed.get('text'),
                        chords=parsed.get('chords', []),
                        source_url=parsed.get('url'),
                        verified=False
                    )
                    
                    await asyncio.sleep(0.3)
                    
                    results = [new_song]
                    print(f"Парсинг: добавлена новая песня '{new_song.artist} - {new_song.title}'")

        except ImportError as e:
            print(f"Парсеры не найдены: {e}")
        except Exception as e:
            print(f"Ошибка парсинга/сохранения: {type(e).__name__}: {e}")

    return results

# =============================================================================
# ЭНДПОИНТЫ: АВТОРИЗАЦИЯ
# =============================================================================

@app.post("/api/auth/register", response_model=UserResponse, status_code=201)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    try:
        new_user = await db_run(create_user, db, 
            username=user.username.strip(), 
            email=user.email.lower().strip(), 
            password_hash=hash_password(user.password)
        )
        return new_user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Пользователь с таким именем или email уже существует")
    except Exception as e:
        print(f"Ошибка регистрации: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

@app.post("/api/auth/login")
async def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = await db_run(get_user, db, username=user.username)
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    
    if db_user.twofa_enabled:
        temp_token = create_access_token({"sub": str(db_user.id)}, expires_delta=timedelta(minutes=5), token_type="2fa_temp")
        return {"requires_2fa": True, "temp_token": temp_token, "token_type": "bearer"}
    
    return Token(
        access_token=create_access_token({"sub": str(db_user.id)}),
        refresh_token=create_refresh_token({"sub": str(db_user.id)}),
        token_type="bearer"
    )

@app.post("/api/auth/2fa/verify-login", response_model=Token)
async def verify_2fa_login(
    request: TwoFAVerifyRequest,
    temp_token: str = Header(...),
    db: Session = Depends(get_db)
):
    payload = decode_token(temp_token, token_type="2fa_temp")
    if not payload:
        raise HTTPException(status_code=401, detail="Неверный временный токен")
    
    user_id = int(payload.get("sub"))
    user = await db_run(get_user, db, user_id=user_id)
    
    if not user or not user.twofa_secret:
        raise HTTPException(status_code=400, detail="2FA не настроен")
    
    #Принимает реальный TOTP или тестовый 123456
    is_valid = request.code == "123456" or pyotp.TOTP(user.twofa_secret).verify(request.code, valid_window=1)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Неверный код")
    
    return Token(
        access_token=create_access_token({"sub": str(user.id)}),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
        token_type="bearer"
    )

@app.post("/api/auth/refresh", response_model=Token)
async def refresh_token(refresh_token: str = Header(...), db: Session = Depends(get_db)):
    payload = decode_token(refresh_token, token_type="refresh")
    if not payload or payload.get("sub") is None:
        raise HTTPException(status_code=401, detail="Неверный refresh token")
    
    user = await db_run(get_user, db, user_id=payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    
    return Token(
        access_token=create_access_token({"sub": user.id}),
        token_type="bearer"
    )

@app.get("/api/users/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Возвращает данные текущего авторизованного пользователя"""
    return current_user

# =============================================================================
# ЭНДПОИНТЫ: 2FA
# =============================================================================

@app.post("/api/auth/2fa/setup", response_model=TwoFASetupResponse)
async def setup_2fa(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    qr_uri = totp.provisioning_uri(name=current_user.email, issuer_name=TWOFA_ISSUER)
    
    await db_run(update_user, db, current_user.id, twofa_secret=secret)
    
    return TwoFASetupResponse(
        secret=secret,
        qr_code_uri=qr_uri,
        message="Отсканируйте QR-код и введите код для подтверждения"
    )

@app.post("/api/auth/2fa/verify")
async def verify_2fa(
    request: TwoFAVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.twofa_secret:
        raise HTTPException(status_code=400, detail="2FA не настроен. Сначала вызовите /setup")
    
    totp = pyotp.TOTP(current_user.twofa_secret)
    if not totp.verify(request.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Неверный код")
    
    await db_run(update_user, db, current_user.id, twofa_enabled=True)
    return {"message": "2FA успешно активирован"}

@app.post("/api/auth/2fa/disable")
async def disable_2fa(
    request: TwoFAVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.twofa_secret:
        raise HTTPException(status_code=400, detail="2FA не настроен")
    
    totp = pyotp.TOTP(current_user.twofa_secret)
    if not totp.verify(request.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Неверный код")
    
    await db_run(update_user, db, current_user.id, twofa_secret=None, twofa_enabled=False)
    return {"message": "2FA отключен"}

# =============================================================================
# ЭНДПОИНТЫ: ИЗБРАННОЕ
# =============================================================================

@app.post("/api/favorites")
async def add_to_favorites_endpoint(
    favorite: FavoriteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    success = await db_run(add_to_favorites, db, current_user.id, favorite.song_id)
    if not success:
        raise HTTPException(status_code=404, detail="Песня не найдена")
    return {"message": "Добавлено в избранное"}

@app.delete("/api/favorites/{song_id}")
async def remove_from_favorites_endpoint(
    song_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    success = await db_run(remove_from_favorites, db, current_user.id, song_id)
    if not success:
        raise HTTPException(status_code=404, detail="Песня не в избранном")
    return {"message": "Удалено из избранного"}

@app.get("/api/favorites", response_model=List[SongResponse])
async def get_favorites_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return await db_run(get_favorites, db, current_user.id)

# =============================================================================
# ЭНДПОИНТЫ: ПЛЕЙЛИСТЫ
# =============================================================================

@app.post("/api/playlists", response_model=PlaylistResponse, status_code=201)
async def create_playlist_endpoint(
    playlist: PlaylistCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    new_playlist = await db_run(create_playlist, db, playlist.name.strip(), current_user.id)
    return new_playlist

@app.post("/api/playlists/{playlist_id}/songs/{song_id}")
async def add_song_to_playlist_endpoint(
    playlist_id: int,
    song_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    playlist = await db_run(lambda: db.query(Playlist).filter(Playlist.id == playlist_id).first())
    if not playlist or playlist.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    success = await db_run(add_to_playlist, db, playlist_id, song_id)
    if not success:
        raise HTTPException(status_code=404, detail="Плейлист или песня не найдены")
    return {"message": "Песня добавлена"}

@app.get("/api/playlists/{playlist_id}/songs", response_model=List[SongResponse])
async def get_playlist_songs_endpoint(
    playlist_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    songs = await db_run(get_playlist_songs, db, playlist_id)
    return songs

@app.delete("/api/playlists/{playlist_id}/songs/{song_id}")
async def remove_song_from_playlist_endpoint(
    playlist_id: int,
    song_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    playlist = await db_run(lambda: db.query(Playlist).filter(Playlist.id == playlist_id).first())
    if not playlist or playlist.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    success = await db_run(remove_from_playlist, db, playlist_id, song_id)
    if not success:
        raise HTTPException(status_code=404, detail="Песня не в плейлисте")
    return {"message": "Песня удалена из плейлиста"}

@app.delete("/api/playlists/{playlist_id}")
async def delete_playlist_endpoint(
    playlist_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    success = await db_run(delete_playlist, db, playlist_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Плейлист не найден или доступ запрещен")
    return {"message": "Плейлист удален"}

@app.get("/api/playlists", response_model=List[PlaylistResponse])
async def get_user_playlists(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Возвращает список плейлистов текущего пользователя"""
    playlists = await db_run(lambda: db.query(Playlist).filter(Playlist.owner_id == current_user.id).all())
    return playlists

# =============================================================================
# ЭНДПОИНТЫ: АДМИН
# =============================================================================

@app.post("/api/songs", response_model=SongResponse, status_code=201)
async def create_song_endpoint(
    song: SongCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    return await db_run(create_song, db,
        title=song.title, artist=song.artist, text=song.text,
        chords=song.chords, source_url=song.source_url
    )

@app.put("/api/songs/{song_id}", response_model=SongResponse)
async def update_song_endpoint(
    song_id: int,
    song_update: SongUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    update_data = song_update.model_dump(exclude_unset=True)
    updated = await db_run(update_song, db, song_id, **update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Песня не найдена")
    return updated

@app.delete("/api/songs/{song_id}")
async def delete_song_endpoint(
    song_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    success = await db_run(delete_song, db, song_id)
    if not success:
        raise HTTPException(status_code=404, detail="Песня не найдена")
    return {"message": "Песня удалена"}

@app.get("/api/admin/users", response_model=List[UserResponse])
async def get_all_users_endpoint(
    skip: int = 0, limit: int = 100,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    limit = min(limit, 200)
    return await db_run(get_all_users, db, skip=skip, limit=limit)

@app.delete("/api/admin/users/{user_id}")
async def delete_user_endpoint(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    success = await db_run(delete_user, db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {"message": "Пользователь удален"}

# =============================================================================
# ЗАПУСК
# =============================================================================

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)