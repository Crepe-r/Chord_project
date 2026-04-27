import requests
from bs4 import BeautifulSoup
import re


BASE_URL = 'https://387.amdm.ru/'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
}


def _parse_artist_title(raw_title: str) -> tuple[str, str]:
    """Вспомогательная функция: разделяет заголовок на артиста и название"""
    raw_title = raw_title.strip()
    if " - " in raw_title:
        parts = raw_title.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].split(",")[0].strip() if len(parts) > 1 else ""
        title = re.split(r'\s*\(', title)[0].strip()
        return artist, title
    return "", raw_title


def website_search_song(query):
    # Формируем URL для поиска
    url = BASE_URL + f"search/?q={query.replace(' ', '+')}"

    try:
        # Делаем запрос
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return []
        
        # Парсим HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        artist_blocks = soup.find_all(class_="artist_name")
        songs = []
        
        for block in artist_blocks:                        
            # Внутри блока ищем ссылку с аккордами
            links = block.find_all('a', href=True)
            title = ""
            for link in links:
                split_url = link['href'].split('/')
                if len(split_url) > 5 and (split_url[5].isdigit()):
                    is_song_url = True
                else: 
                    is_song_url = False

                if not is_song_url:
                    title += link.text.strip()
                

                if link and ('/akkordi/' in link['href']) and (is_song_url):
                    # Проверяем наличие иконки подтверждения внутри этого же блока
                    confirm_icon = block.find('span', class_="fa fa-check-circle tooltip")
                    
                    # Если есть подтверждение - добавляем
                    title += (' ' + link.text.strip())
                
                    href = link['href']
                    full_url = href if href.startswith('http') else 'https://amdm.ru' + href
                    
                    songs.append({
                        'title': title,
                        'url': full_url,
                        'verified': True if confirm_icon else False
                    })  
                    if len(songs) == 10:
                        return songs        
        if songs:
            return songs
    except Exception:
        return []


def get_song_data(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        text_blocks = soup.find_all('pre')

        # Текст
        text = "\n".join(map(lambda text_block: text_block.text, text_blocks)) if text_blocks else 'Текст не найден'

        # Название песни (из <title>)
        title_tag = soup.find('title')
        raw_title = title_tag.text if title_tag else 'Неизвестно'
        
        artist, song_title = _parse_artist_title(raw_title)
        
        # Если не удалось распарсить — пробуем из h1 на странице
        if not artist or not song_title:
            h1 = soup.find('h1')
            if h1:
                artist, song_title = _parse_artist_title(h1.text.strip())
        
        if not artist:
            artist = 'Неизвестный исполнитель'
        if not song_title:
            song_title = raw_title

        # Аккорды
        chords = list(map(lambda div: div['data-chord'].lower(), soup.find_all(class_="podbor__chord")))
        chords = [re.sub(r'^([a-g][#b]?).*$', r'\1', chord.lower()) for chord in chords]
        
        return {
            'artist': artist,
            'title': song_title,
            'text': text,
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
    
    # Получаем текст
    song_data = get_song_data(selected_song['url'])
    
    # Добавляем информацию о подтверждении в результат
    if song_data:
        song_data['verified'] = selected_song['verified']
    
    return song_data


if __name__ == "__main__":
    result = search_song("Вахтерам")
    
    if result:
        print(result)