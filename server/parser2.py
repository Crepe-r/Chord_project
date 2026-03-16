import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

BASE_URL = "https://chorder.ru"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

def website_search_song(query):
    """
    Поиск песни на сайте chorder.ru
    """
    url = f"https://chorder.ru/search?q={query}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            print(f"Ошибка: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')

        # Находим все элементы с классом "item" (каждая песня в отдельном блоке)
        items = soup.find_all('div', class_='item')

        songs = []
        query_words = query.lower().split()

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
            
            # Полное название для поиска
            full_title = f"{artist} {song_title}".lower()
            
            # Проверяем, содержит ли полное название ВСЕ слова из запроса
            matches_all_words = all(word in full_title for word in query_words)
            
            # Если все слова нашлись - добавляем песню
            if matches_all_words:
                href = link['href']
                full_url = urljoin(BASE_URL, href)
                
                songs.append({
                    'title': f"{artist} - {song_title}" if artist else song_title,
                    'artist': artist,
                    'song_title': song_title,
                    'url': full_url,
                })
        
        return songs

    except Exception as e:
        print(f"Ошибка при поиске: {e}")
        return []


def get_chords(text):
    """
    Извлекает  аккорды из текста песни
    
    """
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
            if re.match(r'^[A-G](#|b)?(?:m|maj|dim|aug|sus)?[0-9]?$', clean_word):
                all_chords.append(clean_word.lower())
        
    return all_chords


def get_song_data(url):
    """
    Получает текст с аккордами со страницы песни
    
    """
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            print(f"Ошибка загрузки: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Название песни
        h1 = soup.find('h1')
        title = h1.text.strip() if h1 else 'Неизвестно'
        
        # Исполнитель
        artist_elem = soup.find('span', class_='artist')
        artist = artist_elem.text.strip() if artist_elem else ""
        
        text_block = soup.find('pre', id='song-text')

        # Получаем весь текст
        text = text_block.get_text()
        
        # Извлекаем аккорды из текста
        chords = get_chords(text)

        return {
            'title': f"{artist} - {title}" if artist else title,
            'text': text,
            'chords': chords, 
            'url': url
        }

    except Exception as e:
        print(f"Ошибка при получении песни: {e}")
        return None


def search_song(query):
    """
    Ищет песню и возвращает первую найденную.
    """
    # Ищем песни
    songs = website_search_song(query)

    if not songs:
        return None

    # Берем первую (самую популярную)
    selected_song = songs[0]

    # Получаем текст песни
    song_data = get_song_data(selected_song['url'])

    return song_data


if __name__ == "__main__":
    result = search_song("кино восьмиклассница")
    
    if result:
        print(result)