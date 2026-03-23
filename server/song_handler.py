import parser1 as p1
import parser2 as p2

NOTES = ['ab','a','a#','bb','b','c','c#','db','d','d#','eb','e','f','f#','gb','g','g#']

def compare_count(c1, c2):
    for offset in range(0,17):
        summa = 0
        count = 0
        for i in range(17):
            if (c1[i]*(c2[offset:] + c2[:offset-1])[i]):
                summa += c1[i]/c2[i]
                count += 1
            elif (c1[i] + c2[i] > 10):
                break
        if 1.4 > ((summa/count) if count != 0 else 0) > 0.6:
            return True
    return False


def chord_counter(chords):
    chord_count = []
    for note in NOTES:
        chord_count.append(chords.count(note))
    return chord_count

def compare_chords(chords_data):
    selected_chords_ind = []

    chords_count = []
    for chords in chords_data:
        chords_count.append(chord_counter(chords[0]))
    
    selected_chords_ind.append(0)

    for ch_ind in range(len(chords_count)):
        if ch_ind not in selected_chords_ind:
            for sel_ind in selected_chords_ind:
                if compare_count(chords_count[ch_ind], chords_count[sel_ind]):
                    break
                else:
                    selected_chords_ind.append(ch_ind)
    return [chords_data[i] for i in selected_chords_ind]
    

def song_handler(query: str):
    songs_data = []

    songs_data.append(p1.search_song(query))
    songs_data.append(p2.search_song(query))

    # print(songs_data)
    songs_data = list(filter(None, songs_data))
    chords_data = [[x['chords'], x['url']] for x in songs_data]
    selected_chords = compare_chords(chords_data)
    return selected_chords

if __name__ == "__main__":
    chords = song_handler("Батарейка")
    print(chords)