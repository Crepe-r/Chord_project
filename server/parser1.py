import requests
from bs4 import BeautifulSoup

def website_search_song(query):
    """
    Поиск песни на сайте amdm.ru
    """
    # Формируем URL для поиска
    url = f"https://amdm.ru/search/?q={query.replace(' ', '+')}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        # Делаем запрос
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"Ошибка: {response.status_code}")
            return []
        
        # Парсим HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        artist_blocks = soup.find_all(class_="artist_name")
        songs = []
        for block in artist_blocks:                        
            # Внутри блока ищем ссылку с аккордами
            links = block.find_all('a', href=True)
            for link in links:
                split_url = link['href'].split('/')
                if len(split_url) > 5 and (split_url[5].isdigit()):
                    is_song_url = True
                else: is_song_url = False
                if link and ('/akkordi/' in link['href']) and (is_song_url):
                    # Проверяем наличие иконки подтверждения внутри этого же блока
                    confirm_icon = block.find('span', class_="fa fa-check-circle tooltip")
                    
                    # Если есть подтверждение - добавляем
                    title = link.text.strip()
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
    except Exception as e:
        print(f"Ошибка при поиске: {e}")
        return []


def get_song_data(url):
    """
    Получает текст с аккордами со страницы песни
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        text_blocks = soup.find_all('pre')

        # Текст
        text = "\n".join(map(lambda text_block: text_block.text, text_blocks))  if text_blocks else 'Текст не найден'


        # Название песни
        title = soup.find('title')
        title_text = title.text if title else 'Неизвестно'
        

        # Аккорды
        chords = list(map(lambda div: div['data-chord'].lower(), soup.find_all(class_ = "podbor__chord")))
        
        
        return {
            'title': title_text,
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
    Сначала ищет среди подтвержденных песен, если нет - берет неподтвержденную.
    """  
    # Ищем песни
    songs = website_search_song(query)
    
    if not songs:
        return None
    
    # Разделяем на подтвержденные и неподтвержденные
    verified_songs = [song for song in songs if song['verified']]
    unverified_songs = [song for song in songs if not song['verified']]
    
    # Выбираем песню: сначала подтвержденные, если есть
    selected_song = verified_songs[0] if verified_songs else unverified_songs[0]
    
    # Получаем текст
    song_data = get_song_data(selected_song['url'])
    
    # Добавляем информацию о подтверждении в результат
    if song_data:
        song_data['verified'] = selected_song['verified']
    
    return song_data


if __name__ == "__main__":
    result = search_song("БИ-2 Кукушка")
    
    if result:
        print(result)