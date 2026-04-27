import parser1 as p1
import parser2 as p2

NOTES = ['AB', 'A', 'A#', 'BB', 'B', 'C', 'C#', 'DB', 'D', 'D#', 'EB', 'E', 'F', 'F#', 'GB', 'G', 'G#']


def compare_count(c1, c2):
    """Сравнивает последовательности аккордов с учётом  сдвига"""
    n = len(c1)
    for offset in range(n):
        c2_rotated = c2[offset:] + c2[:offset]
        
        summa = 0.0
        count = 0
        
        for i in range(n):
            val1 = c1[i]
            val2 = c2_rotated[i]
            
            if val1 > 0 and val2 > 0:
                summa += val1 / val2
                count += 1
                
        if count == 0:
            continue
            
        ratio = summa / count
        if 0.6 < ratio < 1.4:
            return True
            
    return False


def chord_counter(chords):
    """Считает частоту каждой ноты из списка аккордов"""
    chords_upper = [c.upper() for c in chords]
    return [chords_upper.count(note) for note in NOTES]


def compare_chords(chords_data):
    """Группирует варианты аккордов по схожести и выбирает лучшую группу"""
    if len(chords_data) <= 1:
        return 0  # Если вариант один — возвращаем его

    chords_count = [chord_counter(chords) for chords in chords_data]
    
    selected_indices = [0]
    selected_counts = [1]

    # Начинаем с 1, т.к. 0 уже добавлен в selected_indices
    for ch_ind in range(1, len(chords_count)):
        matched = False
        for idx, sel_ind in enumerate(selected_indices):
            if compare_count(chords_count[ch_ind], chords_count[sel_ind]):
                selected_counts[idx] += 1
                matched = True
                break
        if not matched:
            selected_indices.append(ch_ind)
            selected_counts.append(1)

    # Возвращаем индекс варианта из самой многочисленной группы
    max_count = max(selected_counts)
    best_group_idx = selected_counts.index(max_count)
    return selected_indices[best_group_idx]
    

def song_handler(query: str):
    songs_data = [p1.search_song(query), p2.search_song(query)]
    songs_data = [s for s in songs_data if s is not None]
    
    if not songs_data:
        return None

    chords_data = [s['chords'] for s in songs_data]
    selected_idx = compare_chords(chords_data)
    
    return songs_data[selected_idx]

if __name__ == "__main__":
    result = song_handler("Вахтерам")
    
    if result:
        print(result)