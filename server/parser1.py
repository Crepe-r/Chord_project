import requests
from bs4 import BeautifulSoup
import re

BASE_URL = 'https://amdm.ru/'
HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

def website_search_song(query): # Поиск песни на сайте amdm.ru
    # Формируем URL для поиска
    clear_query = re.sub(r'[^\w\s]', '', query)
    url = BASE_URL + f"search/?q={query.replace(' ', '+')}"

    try:
        # Делаем запрос
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"Ошибка: {response.status_code}")
            return []
        
        # Парсим HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        artist_blocks = soup.find_all(class_="artist_name")
        songs = []
        query_words = clear_query.lower().split()
        for block in artist_blocks:                        
            # Внутри блока ищем ссылку с аккордами
            links = block.find_all('a', href=True)
            title = ""
            for link in links:
                split_url = link['href'].split('/')
                if len(split_url) > 5 and (split_url[5].isdigit()):
                    is_song_url = True
                else: is_song_url = False

                if not is_song_url:
                    title += link.text.strip()
                

                if link and ('/akkordi/' in link['href']) and (is_song_url):
                    # Проверяем наличие иконки подтверждения внутри этого же блока
                    confirm_icon = block.find('span', class_="fa fa-check-circle tooltip")
                    
                    # Если есть подтверждение - добавляем
                    title += (' ' + link.text.strip())
                    test_title = re.sub(r'[^\w\s]', '', title).lower()

                    matches_all_words = 0
                    
                    if test_title.split() == query_words:
                        matches_all_words += 1

                    if all(word in test_title for word in query_words):
                        matches_all_words += 1

                    if matches_all_words:
                        href = link['href']
                        full_url = href if href.startswith('http') else 'https://amdm.ru' + href
                        
                        songs.append({
                            'title': title,
                            'url': full_url,
                            'verified': True if confirm_icon else False,
                            'priority': matches_all_words
                        })  
                        if len(songs) == 10:
                            return songs        
        if songs:
            return songs
    except Exception as e:
        print(f"Ошибка при поиске: {e}")
        return []


def get_song_data(url): #Получение текста с аккордами со страницы песни
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
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
        chords = [re.sub(r'^([a-g][#b]?).*$', r'\1', chord.lower()) for chord in chords]
        
        return {
            'title': title_text,
            'text': text,
            'chords': chords,
            'url': url
        }
        
    except Exception as e:
        print(f"Ошибка при получении песни: {e}")
        return None


def search_song(query): # Поиски песни
    # Ищем песни
    songs = website_search_song(query)
    
    if not songs:
        return None
    
    priority_song = [song for song in songs if song['priority'] == 2]

    if not priority_song:
        priority_song = [song for song in songs if song['priority'] == 1]

    if not priority_song:
        priority_song = songs

    # Разделяем на подтвержденные и неподтвержденные
    verified_songs = [song for song in priority_song if song['verified']]
    unverified_songs = [song for song in priority_song if not song['verified']]
    
    # Выбираем песню: сначала подтвержденные, если есть
    selected_song = verified_songs[0] if verified_songs else unverified_songs[0]
    
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