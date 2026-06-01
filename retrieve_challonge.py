import requests
import re
import sys
import time
import csv

challongekeyfile = open('challonge.key')
challongekey = challongekeyfile.read().strip()
challongekeyfile.close()

challonge_regex = re.compile(r'(([\w\-]+)\.)?challonge\.com/([\w\-]+)')
challonge_scores_regex = re.compile(r'(-1|0|[1-9][0-9]*)-(-1|0|[1-9][0-9]*)')

class NoChallongeMatchError(Exception):
    pass

def extract_challonge_slug(url):
    ch_match = challonge_regex.search(url)

    if ch_match is None:
        print('no match')
        raise NoChallongeMatchError

    else:
        if ch_match.group(2) is None:
            return ch_match.group(3)
        else:
            return '{}-{}'.format(ch_match.group(2), ch_match.group(3))

def get_placings_raw(challonge_slug):
    url = 'https://api.challonge.com/v1/tournaments/{}/participants.json?api_key={}'.format(challonge_slug, challongekey)

    data = request_challonge(url)

    return [{'placement': placing_data['participant']['final_rank'], 'id': str(placing_data['participant']['id']), 'tag': placing_data['participant']['name'], 'other_ids': placing_data['participant']['group_player_ids']} for placing_data in data]


def get_sets_raw(challonge_slug, tags={}):
    url = 'https://api.challonge.com/v1/tournaments/{}/matches.json?api_key={}'.format(challonge_slug, challongekey)

    data = request_challonge(url)

    sets = []

    for set_ in data:
        set_data = set_['match']
        p1_id = str(set_data['player1_id'])
        p2_id = str(set_data['player2_id'])

        p1_tag = tags.get(p1_id, p1_id)
        p2_tag = tags.get(p2_id, p2_id)

        scores_match = challonge_scores_regex.fullmatch(set_data['scores_csv'])

        sets.append({'id': str(set_data['id']), 'winner': str(set_data['winner_id']) if set_data['winner_id'] is not None else None, 'p1_id': p1_id, 'p1_tag': p1_tag, 'p1_score': scores_match.group(1) if scores_match is not None else None,
            'p2_id': p2_id, 'p2_tag': p2_tag, 'p2_score': scores_match.group(2) if scores_match is not None else None})

    return sets


def request_challonge(url, quiet=False):
    progress = False

    tries = 0

    while not progress:

        try:
            response = requests.get(url, headers={'User-Agent': 'UltRank App'})

            if response.status_code == 200:
                response_json = response.json()
                progress = True
            else:
                tries += 1
                if not quiet:
                    print(f'try {tries}: received non-200 response... sleeping then trying again... ', end='', flush=True)
                    print(response.text)
                    print(response.status_code)

                time.sleep(60)
                if not quiet:
                    print('retrying')

        except Exception as e:
            tries += 1
            if not quiet:
                print(f'try {tries}: requests failure... sleeping then trying again... ', end='', flush=True)
                print(e)
            time.sleep(60)
            if not quiet:
                print('retrying')

    return response_json


def get_challonge_data_with_id_to_id_match(slug, id_map):
    tags = {}
    placings = []
    sets = []

    group_id_map = {}
    id_map_l = id_map.copy()

    with open('tour_placements.csv', mode='w', newline='', encoding='utf-8') as placements_file:
        p_writer = csv.DictWriter(placements_file, fieldnames=['placement', 'id', 'tag', 'challonge_id'])
        p_writer.writeheader()

        placings_t = get_placings_raw(slug)

        for placing in placings_t:
            tags[placing['id']] = placing['tag']

            for id_ in placing['other_ids']:
                tags[str(id_)] = placing['tag']
                id_map_l[str(id_)] = id_map_l[placing['id']]
                group_id_map[str(id_)] = placing['id']

            placings.append({'placement': placing['placement'], 'id': id_map_l.get(placing['id'], placing['id']), 'tag': placing['tag'], 'challonge_id': placing['id']})

    with open('tour_sets.csv', mode='w', newline='', encoding='utf-8') as sets_file:
        s_writer = csv.DictWriter(sets_file, fieldnames=['id', 'winner', 'p1_id', 'p1_tag', 'p1_score', 'p2_id', 'p2_tag', 'p2_score', 'winner_challonge', 'p1_id_challonge', 'p2_id_challonge'])
        s_writer.writeheader()

        sets_t = get_sets_raw(slug, tags)

        for set_ in sets_t:
            sets.append({'id': set_['id'], 'winner': id_map_l.get(set_['winner'], set_['winner']),
                'p1_id': id_map_l.get(set_['p1_id'], set_['p1_id']), 'p1_tag': set_['p1_tag'], 'p1_score': set_['p1_score'],
                'p2_id': id_map_l.get(set_['p2_id'], set_['p2_id']), 'p2_tag': set_['p2_tag'], 'p2_score': set_['p2_score'],
                'winner_challonge': group_id_map.get(set_['winner'], set_['winner']),
                'p1_id_challonge': group_id_map.get(set_['p1_id'], set_['p1_id']),
                'p2_id_challonge': group_id_map.get(set_['p2_id'], set_['p2_id'])})

    return placings, sets

def get_challonge_data_with_name_to_id_match(slug, id_map):
    tags = {}
    id_to_id_map = {}

    group_id_map = {}

    with open(f'tournament_info/{slug}.csv', mode='w', newline='', encoding='utf-8') as placements_file:
        p_writer = csv.DictWriter(placements_file, fieldnames=['placement', 'id', 'tag', 'challonge_id'])
        p_writer.writeheader()

        placings = get_placings_raw(slug)

        for placing in placings:
            tags[placing['id']] = placing['tag']

            id_to_id_map[placing['id']] = id_map.get(placing['tag'], placing['id'])

            for id_ in placing['other_ids']:
                tags[str(id_)] = placing['tag']
                id_to_id_map[str(id_)] = id_map.get(placing['tag'], placing['id'])
                group_id_map[str(id_)] = placing['id']

            p_writer.writerow({'placement': placing['placement'], 'id': id_map.get(placing['tag'], placing['tag']), 'tag': placing['tag'], 'challonge_id': placing['id']})


    with open(f'tournament_info/{slug}_sets.csv', mode='w', newline='', encoding='utf-8') as sets_file:
        s_writer = csv.DictWriter(sets_file, fieldnames=['id', 'winner', 'p1_id', 'p1_tag', 'p1_score', 'p2_id', 'p2_tag', 'p2_score', 'winner_challonge', 'p1_id_challonge', 'p2_id_challonge'])
        s_writer.writeheader()

        sets = get_sets_raw(slug, tags)

        for set_ in sets:
            s_writer.writerow({'id': set_['id'], 'winner': id_to_id_map.get(set_['winner'], set_['winner']),
                'p1_id': id_to_id_map.get(set_['p1_id'], set_['p1_id']), 'p1_tag': set_['p1_tag'], 'p1_score': set_['p1_score'],
                'p2_id': id_to_id_map.get(set_['p2_id'], set_['p2_id']), 'p2_tag': set_['p2_tag'], 'p2_score': set_['p2_score'],
                'winner_challonge': group_id_map.get(set_['winner'], set_['winner']),
                'p1_id_challonge': group_id_map.get(set_['p1_id'], set_['p1_id']),
                'p2_id_challonge': group_id_map.get(set_['p2_id'], set_['p2_id'])})


if __name__ == '__main__':
    url = input('input challonge url: ')
    slug = extract_challonge_slug(url)

    map_filepath = input('id map file: ')
    try:
        map_file = open('tournament_info/' + map_filepath, newline='')
        reader = csv.DictReader(map_file)

        fieldnames = reader.fieldnames

        print('Columns: ')

        for i, name in enumerate(fieldnames):
            print(f'{i} - {name}')

        tag_col = int(input('Which column # is the tag? '))
        id_col = int(input('Which column # is the id? '))

        tag_field = fieldnames[tag_col]
        id_field = fieldnames[id_col]

        tag_to_id_dict = {}
        duplicate_tags = set()

        for row in reader:
            if row[tag_field] in duplicate_tags:
                continue
            if row[tag_field] in tag_to_id_dict.keys():
                print(f'{row[tag_field]} is a duplicate tag, all instances of id conversion will be ignored')
                duplicate_tags.add(row[tag_field])
                tag_to_id_dict.pop(row[tag_field])
            else:
                tag_to_id_dict[row[tag_field]] = row[id_field]
    except:
        tag_to_id_dict ={}

    get_challonge_data_with_name_to_id_match(slug, tag_to_id_dict)
