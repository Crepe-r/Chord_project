import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re


BASE_URL = "https://chorder.ru/"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9',
    'Connection': 'keep-alive',
}


def website_search_song(query):
    url = BASE_URL + f"search?q={requests.utils.quote(query)}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')

        # Находим все элементы с классом "item" 
        items = soup.find_all('div', class_='item')

        songs = []

        for item in items:
            # Название песни и ссылка
            title_div = item.find('div', class_='title')
            if not title_div:
                continue
                
            link = title_div.find('a', href=True)
            if not link:
                continue
                
            song_title = link.text.strip()
            
            # Исполнитель
            artist_div = item.find('div', class_='artist')
            artist = artist_div.text.strip() if artist_div else ""
            
            href = link['href']
            full_url = urljoin(BASE_URL, href)
            
            songs.append({
                'title': song_title,
                'artist': artist,
                'url': full_url,
                'verified': False  # chorder.ru не предоставляет флаг верификации
            })
            
            if len(songs) >= 10:
                return songs
        
        return songs

    except Exception:
        return []


def get_chords(text):
    """Извлекает аккорды из текста"""
    all_chords = []
    
    # Разбиваем текст на строки
    lines = text.split('\n')
    
    for line in lines:
        # Разбиваем на слова и проверяем каждое
        words = line.split()
        for word in words:
            # Очищаем слово от знаков препинания
            clean_word = re.sub(r'^[^\w#b]+|[^\w#b]+$', '', word)
            if not clean_word:
                continue
            
            # Проверяем, похоже ли слово на аккорд
            if re.match(r'^[A-G](#|b)?(?:m|maj|dim|aug|sus)?[0-9]?$', clean_word, re.I):
                chord_norm = re.sub(r'^([a-g][#b]?).*$', r'\1', clean_word, flags=re.I).upper()
                all_chords.append(chord_norm) 
        
    return all_chords


def get_song_data(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Название песни
        h1 = soup.find('h1')
        raw_title = h1.text.strip() if h1 else 'Неизвестно'
        
        # Исполнител
        h3_artist = soup.find('h3', class_='song-artist')
        artist = h3_artist.text.strip() if h3_artist else ''
        
        if not artist and " - " in raw_title:
            parts = raw_title.split(" - ", 1)
            artist = parts[0].strip()
            title = parts[1].split(",")[0].strip() if len(parts) > 1 else raw_title
        else:
            title = raw_title
        
        text_block = soup.find('pre', id='song-text')
        text = text_block.get_text() if text_block else 'Текст не найден'
        
        # Извлекаем аккорды из текста
        chords = get_chords(text)

        return {
            'artist': artist if artist else 'Неизвестный исполнитель',
            'title': title if title else raw_title,
            'text': text.strip(),
            'chords': chords,  
            'url': url
        }

    except Exception:
        return None


def search_song(query):
    # Ищем песни
    songs = website_search_song(query)

    if not songs:
        return None
    

    selected_song = songs[0]

    # Получаем текст песни
    song_data = get_song_data(selected_song['url'])

    return song_data


if __name__ == "__main__":
    result = search_song("Вахтерам")
    
    if result:
        print(result)