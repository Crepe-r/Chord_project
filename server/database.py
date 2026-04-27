from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Table, Text, Boolean, DateTime, event
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session, joinedload
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from datetime import datetime
import os
import json
import re
import BD_login  

# =============================================================================
# ПОДКЛЮЧЕНИЕ К БД
# =============================================================================
DATABASE_URL = os.getenv('DATABASE_URL', f'postgresql://chordfinder_user:{BD_login.password}@localhost:5432/chordfinder')

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# =============================================================================
# ТАБЛИЦЫ СВЯЗИ (M2M)
# =============================================================================
user_favorites = Table('user_favorites', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), index=True, nullable=False),
    Column('song_id', Integer, ForeignKey('songs.id'), index=True, nullable=False),
    schema=None  
)

playlist_songs = Table('playlist_songs', Base.metadata,
    Column('playlist_id', Integer, ForeignKey('playlists.id'), index=True, nullable=False),
    Column('song_id', Integer, ForeignKey('songs.id'), index=True, nullable=False),
    schema=None
)


# =============================================================================
# МОДЕЛИ
# =============================================================================

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default='user', nullable=False)  # user, admin
    twofa_secret = Column(String(32), nullable=True)
    twofa_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Отношения
    favorites = relationship('Song', secondary=user_favorites, back_populates='favorited_by', lazy='select')
    playlists = relationship('Playlist', back_populates='owner', cascade='all, delete-orphan', lazy='select')
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
    
    def to_dict(self, exclude_fields=None):
        """Сериализация пользователя в dict (для API ответов)"""
        exclude = exclude_fields or ['password_hash', 'twofa_secret']
        return {
            c.name: getattr(self, c.name) 
            for c in self.__table__.columns 
            if c.name not in exclude
        }


class Song(Base):
    __tablename__ = 'songs'
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Основные поля
    title = Column(String(200), nullable=False, index=True)   # название песни
    artist = Column(String(200), nullable=False, index=True)  # исполнитель
    
    # Контент
    text = Column(Text, nullable=True)
    chords = Column(Text, nullable=True)  
    source_url = Column(String(500), nullable=True)
    
    # Метаданные
    hits = Column(Integer, default=0, nullable=False)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Отношения
    favorited_by = relationship('User', secondary=user_favorites, back_populates='favorites', lazy='select')
    in_playlists = relationship('Playlist', secondary=playlist_songs, back_populates='songs', lazy='select')
    
    def __repr__(self):
        return f"<Song(id={self.id}, title='{self.title}', artist='{self.artist}')>"
    
    def get_chords(self) -> list:
        """Возвращает список аккордов из JSON"""
        if not self.chords:
            return []
        try:
            return json.loads(self.chords)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_chords(self, chords_list: list):
        """Сохраняет список аккордов как JSON"""
        if isinstance(chords_list, list):
            self.chords = json.dumps(chords_list, ensure_ascii=False)
        elif isinstance(chords_list, str):

            try:
                json.loads(chords_list)
                self.chords = chords_list
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON string for chords")
    
    def get_full_name(self) -> str:
        """Возвращает полное имя для отображения: 'Artist - Title'"""
        return f"{self.artist} - {self.title}"
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'artist': self.artist,
            'text': self.text,
            'chords': self.get_chords(),
            'source_url': self.source_url,
            'hits': self.hits,
            'verified': self.verified,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Playlist(Base):
    __tablename__ = 'playlists'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    owner = relationship('User', back_populates='playlists', lazy='select')
    songs = relationship('Song', secondary=playlist_songs, back_populates='in_playlists', lazy='select')
    
    def __repr__(self):
        return f"<Playlist(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"
    
    def to_dict(self, with_songs=False):
        data = {
            'id': self.id,
            'name': self.name,
            'owner_id': self.owner_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if with_songs:
            data['songs'] = [song.to_dict() for song in self.songs]
        return data


# =============================================================================
# ИНИЦИАЛИЗАЦИЯ И СЕССИИ
# =============================================================================

def init_db():
    """Создаёт все таблицы """
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ База данных инициализирована")
        return True
    except SQLAlchemyError as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        return False


def get_db():
    """Генератор сессий для FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# ПОЛЬЗОВАТЕЛИ
# =============================================================================

def _validate_email(email: str) -> bool:
    """Простая валидация email"""
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None


def _validate_username(username: str) -> bool:
    """Валидация имени пользователя"""
    return 3 <= len(username) <= 50 and username.isalnum() or '_' in username


def create_user(db: Session, username: str, email: str, password_hash: str, role: str = 'user') -> User:
    """Создаёт нового пользователя с валидацией"""
    if not _validate_username(username):
        raise ValueError("Username must be 3-50 chars, alphanumeric or underscore")
    if not _validate_email(email):
        raise ValueError("Invalid email format")
    if role not in ('user', 'admin'):
        raise ValueError("Invalid role")
    
    try:
        # Проверка на дубликаты
        if db.query(User).filter((User.username == username) | (User.email == email)).first():
            raise IntegrityError("User with this username or email already exists", None, None)
        
        user = User(
            username=username.strip(),
            email=email.lower().strip(),
            password_hash=password_hash,
            role=role
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise RuntimeError(f"Database error: {e}")


def get_user(db: Session, user_id: int = None, username: str = None, email: str = None) -> User:
    """Получает пользователя по ID, username или email"""
    query = db.query(User)
    if user_id:
        return query.filter(User.id == user_id).first()
    if username:
        return query.filter(User.username.ilike(username)).first()
    if email:
        return query.filter(User.email.ilike(email)).first()
    return None


def get_all_users(db: Session, skip: int = 0, limit: int = 100):
    """Пагинация списка пользователей"""
    return db.query(User).order_by(User.created_at.desc()).offset(skip).limit(limit).all()


def delete_user(db: Session, user_id: int) -> bool:
    """Удаляет пользователя"""
    try:
        user = get_user(db, user_id=user_id)
        if user:
            db.delete(user)
            db.commit()
            return True
        return False
    except SQLAlchemyError:
        db.rollback()
        return False


def update_user(db: Session, user_id: int, **kwargs) -> User:
    """Обновляет данные пользователя"""
    user = get_user(db, user_id=user_id)
    if not user:
        return None
    
    allowed = ['username', 'email', 'role', 'twofa_secret', 'twofa_enabled']
    try:
        for key, value in kwargs.items():
            if key in allowed and value is not None:
                if key == 'email' and not _validate_email(value):
                    continue 
                setattr(user, key, value)
        db.commit()
        db.refresh(user)
        return user
    except SQLAlchemyError:
        db.rollback()
        raise


# =============================================================================
# ПЕСНИ
# =============================================================================

def create_song(db: Session, title: str, artist: str, text: str = None, 
                chords: list = None, source_url: str = None, verified: bool = False) -> Song:
    """Создаёт новую песню"""
    if not title or not artist:
        raise ValueError("Title and artist are required")
    
    try:
        song = Song(
            title=title.strip(),
            artist=artist.strip(),
            text=text,
            source_url=source_url,
            verified=verified
        )
        if chords:
            song.set_chords(chords)
        db.add(song)
        db.commit()
        db.refresh(song)
        return song
    except SQLAlchemyError as e:
        db.rollback()
        raise RuntimeError(f"Failed to create song: {e}")


def get_song(db: Session, song_id: int = None, title: str = None, artist: str = None) -> Song:
    """Поиск песни по ID или по названию + исполнителю"""
    if song_id:
        return db.query(Song).filter(Song.id == song_id).first()
    if title and artist:
        return db.query(Song).filter(
            Song.title.ilike(title.strip()), 
            Song.artist.ilike(artist.strip())
        ).first()
    return None


def search_songs(db: Session, query: str, limit: int = 20, skip: int = 0):
    """Поиск по названию и исполнителю"""
    if not query:
        return []
    search = f"%{query.strip()}%"
    return db.query(Song).filter(
        Song.title.ilike(search) | Song.artist.ilike(search)
    ).order_by(Song.hits.desc()).offset(skip).limit(limit).all()


def get_all_songs(db: Session, skip: int = 0, limit: int = 100, order_by: str = 'hits'):
    """Пагинация списка песен с сортировкой"""
    query = db.query(Song)
    if order_by == 'hits':
        query = query.order_by(Song.hits.desc())
    elif order_by == 'created_at':
        query = query.order_by(Song.created_at.desc())
    elif order_by == 'title':
        query = query.order_by(Song.title.asc())
    return query.offset(skip).limit(limit).all()


def update_song(db: Session, song_id: int, **kwargs) -> Song:
    """Обновляет информацию о песне"""
    song = get_song(db, song_id=song_id)
    if not song:
        return None
    
    allowed_fields = ['title', 'artist', 'text', 'chords', 'source_url', 'verified']
    try:
        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                if key == 'chords':
                    song.set_chords(value)  
                else:
                    setattr(song, key, value)
        db.commit()
        db.refresh(song)
        return song
    except SQLAlchemyError:
        db.rollback()
        raise


def delete_song(db: Session, song_id: int) -> bool:
    """Удаляет песню"""
    try:
        song = get_song(db, song_id=song_id)
        if song:
            db.delete(song)
            db.commit()
            return True
        return False
    except SQLAlchemyError:
        db.rollback()
        return False


def increment_song_hits(db: Session, song_id: int) -> bool:
    """Увеличивает счётчик просмотров"""
    try:
        result = db.query(Song).filter(Song.id == song_id).update(
            {Song.hits: Song.hits + 1},
            synchronize_session='fetch'
        )
        db.commit()
        return result > 0
    except SQLAlchemyError:
        db.rollback()
        return False


# =============================================================================
# ИЗБРАННОЕ
# =============================================================================

def add_to_favorites(db: Session, user_id: int, song_id: int) -> bool:
    """Добавляет песню в избранное"""
    try:
        user = get_user(db, user_id=user_id)
        song = get_song(db, song_id=song_id)
        if not (user and song):
            return False
        if song not in user.favorites:
            user.favorites.append(song)
            db.commit()
        return True
    except SQLAlchemyError:
        db.rollback()
        return False


def remove_from_favorites(db: Session, user_id: int, song_id: int) -> bool:
    """Удаляет песню из избранного"""
    try:
        user = get_user(db, user_id=user_id)
        song = get_song(db, song_id=song_id)
        if user and song and song in user.favorites:
            user.favorites.remove(song)
            db.commit()
            return True
        return False
    except SQLAlchemyError:
        db.rollback()
        return False


def get_favorites(db: Session, user_id: int, with_eager: bool = True):
    """Возвращает избранные песни пользователя"""
    if with_eager:
        user = db.query(User).options(
            joinedload(User.favorites)
        ).filter(User.id == user_id).first()
    else:
        user = get_user(db, user_id=user_id)
    return user.favorites if user else []


# =============================================================================
# ПЛЕЙЛИСТЫ
# =============================================================================

def create_playlist(db: Session, name: str, owner_id: int) -> Playlist:
    """Создаёт новый плейлист"""
    if not name or not owner_id:
        raise ValueError("Name and owner_id are required")
    
    try:
        playlist = Playlist(name=name.strip(), owner_id=owner_id)
        db.add(playlist)
        db.commit()
        db.refresh(playlist)
        return playlist
    except SQLAlchemyError as e:
        db.rollback()
        raise RuntimeError(f"Failed to create playlist: {e}")


def get_playlist(db: Session, playlist_id: int, with_owner: bool = True) -> Playlist:
    """Получает плейлист по ID"""
    query = db.query(Playlist)
    if with_owner:
        query = query.options(joinedload(Playlist.owner))
    return query.filter(Playlist.id == playlist_id).first()


def add_to_playlist(db: Session, playlist_id: int, song_id: int) -> bool:
    """Добавляет песню в плейлист"""
    try:
        playlist = get_playlist(db, playlist_id, with_owner=False)
        song = get_song(db, song_id=song_id)
        if playlist and song and song not in playlist.songs:
            playlist.songs.append(song)
            db.commit()
            return True
        return False
    except SQLAlchemyError:
        db.rollback()
        return False


def remove_from_playlist(db: Session, playlist_id: int, song_id: int) -> bool:
    """Удаляет песню из плейлиста"""
    try:
        playlist = get_playlist(db, playlist_id, with_owner=False)
        song = get_song(db, song_id=song_id)
        if playlist and song and song in playlist.songs:
            playlist.songs.remove(song)
            db.commit()
            return True
        return False
    except SQLAlchemyError:
        db.rollback()
        return False


def get_playlist_songs(db: Session, playlist_id: int, skip: int = 0, limit: int = 100):
    """Пагинация песен в плейлисте"""
    playlist = get_playlist(db, playlist_id, with_owner=False)
    if not playlist:
        return []
    return playlist.songs[skip:skip+limit]


def delete_playlist(db: Session, playlist_id: int, user_id: int = None) -> bool:
    """Удаляет плейлист"""
    try:
        playlist = get_playlist(db, playlist_id, with_owner=False)
        if not playlist:
            return False
        if user_id and playlist.owner_id != user_id:
            # Проверка прав 
            admin = get_user(db, user_id=user_id)
            if not admin or admin.role != 'admin':
                return False
        db.delete(playlist)
        db.commit()
        return True
    except SQLAlchemyError:
        db.rollback()
        return False


# =============================================================================
# ФУНКЦИИ
# =============================================================================

def get_stats(db: Session) -> dict:
    """Быстрая статистика по БД"""
    return {
        'users_count': db.query(User).count(),
        'songs_count': db.query(Song).count(),
        'playlists_count': db.query(Playlist).count(),
        'verified_songs': db.query(Song).filter(Song.verified == True).count()
    }